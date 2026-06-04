from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.client_ip import client_ip
from app.core.session import sessions
from app.db.models import (
    GameHubUser,
    MessengerChat,
    MessengerChatMember,
    MessengerDiamondLedger,
    MessengerFriendship,
    MessengerMessage,
    UserLastIp,
)
from app.db.session import get_db
from app.integrations.users_api import sync_diamonds_to_sessions, users_api
from app.messaging.push import push_to_users

router = APIRouter(prefix="/api/messenger", tags=["messenger"])


def _ordered_pair(a: int, b: int) -> tuple[int, int]:
    return (a, b) if a < b else (b, a)


def _dm_peer_key(a: int, b: int) -> str:
    x, y = _ordered_pair(a, b)
    return f"{x}:{y}"


def _commission(amount: int) -> int:
    d = (Decimal(int(amount)) * Decimal("0.20")).to_integral_value(rounding=ROUND_HALF_UP)
    return int(d)


def _auth_gamehub_user(authorization: str = Header(default=""), db: Session = Depends(get_db)) -> GameHubUser:
    token = authorization.replace("Bearer ", "").strip()
    sess = sessions.get(token)
    if sess is None or sess.username == "admindb":
        raise HTTPException(status_code=401, detail="Unauthorized")
    u = db.query(GameHubUser).filter(GameHubUser.username == sess.username).first()
    if u is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return u


def _touch_last_ip(db: Session, user_id: int, ip: str) -> None:
    if not ip:
        return
    now = datetime.now(timezone.utc)
    row = db.query(UserLastIp).filter(UserLastIp.user_id == user_id).first()
    if row:
        row.ip = ip
        row.updated_at = now
    else:
        db.add(UserLastIp(user_id=user_id, ip=ip, updated_at=now))


def get_messenger_user(request: Request, db: Session = Depends(get_db), user: GameHubUser = Depends(_auth_gamehub_user)) -> GameHubUser:
    _touch_last_ip(db, user.id, client_ip(request))
    db.commit()
    return user


# --- search ---


@router.get("/users/search")
async def search_users(
    q: str = Query("", min_length=0, max_length=64),
    db: Session = Depends(get_db),
    me: GameHubUser = Depends(get_messenger_user),
) -> dict:
    term = (q or "").strip()
    if len(term) < 1:
        return {"users": []}
    rows = (
        db.query(GameHubUser)
        .filter(GameHubUser.id != me.id)
        .filter(GameHubUser.username.ilike(f"{term}%"))
        .order_by(GameHubUser.username.asc())
        .limit(30)
        .all()
    )
    return {"users": [{"id": r.id, "username": r.username} for r in rows]}


# --- friends ---


@router.get("/friends")
async def list_friends(db: Session = Depends(get_db), me: GameHubUser = Depends(get_messenger_user)) -> dict:
    rows = (
        db.query(MessengerFriendship)
        .filter(
            or_(MessengerFriendship.user_a == me.id, MessengerFriendship.user_b == me.id),
            MessengerFriendship.status == "accepted",
        )
        .all()
    )
    peer_ids: list[int] = []
    for r in rows:
        peer_ids.append(r.user_b if r.user_a == me.id else r.user_a)
    if not peer_ids:
        return {"friends": []}
    users = {u.id: u for u in db.query(GameHubUser).filter(GameHubUser.id.in_(peer_ids)).all()}
    out = []
    for pid in peer_ids:
        u = users.get(pid)
        if u:
            out.append({"id": u.id, "username": u.username})
    out.sort(key=lambda x: x["username"].lower())
    return {"friends": out}


@router.get("/friends/pending")
async def friends_pending(db: Session = Depends(get_db), me: GameHubUser = Depends(get_messenger_user)) -> dict:
    """Входящие заявки (не я инициатор) и исходящие (я инициатор), status=pending."""
    rows = (
        db.query(MessengerFriendship)
        .filter(
            or_(MessengerFriendship.user_a == me.id, MessengerFriendship.user_b == me.id),
            MessengerFriendship.status == "pending",
        )
        .all()
    )
    incoming: list[dict] = []
    outgoing: list[dict] = []
    peer_ids = [r.user_b if r.user_a == me.id else r.user_a for r in rows]
    users = {u.id: u for u in db.query(GameHubUser).filter(GameHubUser.id.in_(peer_ids)).all()} if peer_ids else {}
    for r in rows:
        pid = r.user_b if r.user_a == me.id else r.user_a
        u = users.get(pid)
        if u is None:
            continue
        item = {"id": u.id, "username": u.username}
        if r.initiator_id == me.id:
            outgoing.append(item)
        else:
            incoming.append(item)
    incoming.sort(key=lambda x: x["username"].lower())
    outgoing.sort(key=lambda x: x["username"].lower())
    return {"incoming": incoming, "outgoing": outgoing}


class FriendUsernameBody(BaseModel):
    username: str = Field(min_length=1, max_length=64)


@router.post("/friends/request")
async def friend_request(
    body: FriendUsernameBody,
    db: Session = Depends(get_db),
    me: GameHubUser = Depends(get_messenger_user),
) -> dict:
    peer = db.query(GameHubUser).filter(GameHubUser.username == body.username.strip()).first()
    if peer is None or peer.id == me.id:
        raise HTTPException(status_code=404, detail="User not found")
    a, b = _ordered_pair(me.id, peer.id)
    existing = db.query(MessengerFriendship).filter(MessengerFriendship.user_a == a, MessengerFriendship.user_b == b).first()
    if existing:
        if existing.status == "accepted":
            return {"status": "already_friends"}
        if existing.status == "pending":
            return {"status": "already_pending"}
    row = MessengerFriendship(user_a=a, user_b=b, status="pending", initiator_id=me.id)
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return {"status": "already_pending"}
    await push_to_users([peer.id], {"type": "friend.request", "from_user_id": me.id, "from_username": me.username})
    return {"status": "ok"}


@router.post("/friends/accept")
async def friend_accept(
    body: FriendUsernameBody,
    db: Session = Depends(get_db),
    me: GameHubUser = Depends(get_messenger_user),
) -> dict:
    peer = db.query(GameHubUser).filter(GameHubUser.username == body.username.strip()).first()
    if peer is None:
        raise HTTPException(status_code=404, detail="User not found")
    a, b = _ordered_pair(me.id, peer.id)
    row = db.query(MessengerFriendship).filter(MessengerFriendship.user_a == a, MessengerFriendship.user_b == b).first()
    if row is None or row.status != "pending":
        raise HTTPException(status_code=400, detail="No pending request")
    if row.initiator_id == me.id:
        raise HTTPException(status_code=400, detail="Cannot accept own request")
    row.status = "accepted"
    db.commit()
    await push_to_users([peer.id], {"type": "friend.accepted", "peer_user_id": me.id, "peer_username": me.username})
    return {"status": "ok"}


@router.delete("/friends/{username}")
async def friend_decline_or_remove(
    username: str,
    db: Session = Depends(get_db),
    me: GameHubUser = Depends(get_messenger_user),
) -> dict:
    peer = db.query(GameHubUser).filter(GameHubUser.username == username.strip()).first()
    if peer is None:
        raise HTTPException(status_code=404, detail="User not found")
    a, b = _ordered_pair(me.id, peer.id)
    row = db.query(MessengerFriendship).filter(MessengerFriendship.user_a == a, MessengerFriendship.user_b == b).first()
    if row:
        db.delete(row)
        db.commit()
    return {"status": "ok"}


# --- chats ---


def _active_member(db: Session, chat_id: int, user_id: int) -> MessengerChatMember | None:
    return (
        db.query(MessengerChatMember)
        .filter(
            MessengerChatMember.chat_id == chat_id,
            MessengerChatMember.user_id == user_id,
            MessengerChatMember.left_at.is_(None),
        )
        .first()
    )


def _chat_member_ids(db: Session, chat_id: int) -> list[int]:
    rows = (
        db.query(MessengerChatMember.user_id)
        .filter(MessengerChatMember.chat_id == chat_id, MessengerChatMember.left_at.is_(None))
        .all()
    )
    return [int(r[0]) for r in rows]


@router.get("/chats")
async def list_chats(db: Session = Depends(get_db), me: GameHubUser = Depends(get_messenger_user)) -> dict:
    q = (
        db.query(MessengerChat, MessengerChatMember)
        .join(MessengerChatMember, MessengerChatMember.chat_id == MessengerChat.id)
        .filter(MessengerChatMember.user_id == me.id, MessengerChatMember.left_at.is_(None))
        .order_by(MessengerChat.last_message_at.desc().nullslast(), MessengerChat.id.desc())
    )
    out = []
    for chat, mem in q.all():
        item: dict = {
            "id": chat.id,
            "type": chat.type,
            "title": chat.title,
            "unread_count": int(mem.unread_count or 0),
            "last_message_at": chat.last_message_at.isoformat() if chat.last_message_at else None,
            "last_message_preview": chat.last_message_preview,
        }
        if chat.type == "dm":
            others = (
                db.query(GameHubUser)
                .join(MessengerChatMember, MessengerChatMember.user_id == GameHubUser.id)
                .filter(
                    MessengerChatMember.chat_id == chat.id,
                    MessengerChatMember.left_at.is_(None),
                    GameHubUser.id != me.id,
                )
                .all()
            )
            if others:
                item["peer"] = {"id": others[0].id, "username": others[0].username}
        out.append(item)
    return {"chats": out}


class CreateDmBody(BaseModel):
    peer_user_id: int = Field(ge=1)


@router.post("/chats/dm")
async def create_or_open_dm(
    body: CreateDmBody,
    db: Session = Depends(get_db),
    me: GameHubUser = Depends(get_messenger_user),
) -> dict:
    if body.peer_user_id == me.id:
        raise HTTPException(status_code=400, detail="Cannot DM self")
    peer = db.query(GameHubUser).filter(GameHubUser.id == body.peer_user_id).first()
    if peer is None:
        raise HTTPException(status_code=404, detail="User not found")
    key = _dm_peer_key(me.id, peer.id)
    chat = db.query(MessengerChat).filter(MessengerChat.dm_peer_key == key).first()
    now = datetime.now(timezone.utc)
    if chat is None:
        chat = MessengerChat(type="dm", title=None, dm_peer_key=key, next_seq=0)
        db.add(chat)
        db.flush()
        db.add(MessengerChatMember(chat_id=chat.id, user_id=me.id, joined_at=now))
        db.add(MessengerChatMember(chat_id=chat.id, user_id=peer.id, joined_at=now))
    else:
        for uid in (me.id, peer.id):
            m = (
                db.query(MessengerChatMember)
                .filter(MessengerChatMember.chat_id == chat.id, MessengerChatMember.user_id == uid)
                .first()
            )
            if m is None:
                db.add(MessengerChatMember(chat_id=chat.id, user_id=uid, joined_at=now))
            else:
                m.left_at = None
                m.joined_at = now
    db.commit()
    return {"chat_id": chat.id}


class CreateGroupBody(BaseModel):
    title: str = Field(min_length=1, max_length=128)
    member_ids: list[int] = Field(default_factory=list)


@router.post("/chats/group")
async def create_group(
    body: CreateGroupBody,
    db: Session = Depends(get_db),
    me: GameHubUser = Depends(get_messenger_user),
) -> dict:
    ids = {me.id}
    for raw in body.member_ids:
        try:
            ids.add(int(raw))
        except (TypeError, ValueError):
            continue
    users = db.query(GameHubUser).filter(GameHubUser.id.in_(list(ids))).all()
    if len(users) != len(ids):
        raise HTTPException(status_code=400, detail="Unknown member id")
    now = datetime.now(timezone.utc)
    chat = MessengerChat(type="group", title=body.title.strip(), dm_peer_key=None, next_seq=0)
    db.add(chat)
    db.flush()
    for u in users:
        db.add(MessengerChatMember(chat_id=chat.id, user_id=u.id, joined_at=now))
    db.commit()
    await push_to_users([u.id for u in users if u.id != me.id], {"type": "chat.updated", "chat_id": chat.id})
    return {"chat_id": chat.id}


class AddMemberBody(BaseModel):
    user_id: int = Field(ge=1)


@router.post("/chats/{chat_id}/members")
async def add_chat_member(
    chat_id: int,
    body: AddMemberBody,
    db: Session = Depends(get_db),
    me: GameHubUser = Depends(get_messenger_user),
) -> dict:
    chat = db.query(MessengerChat).filter(MessengerChat.id == chat_id).first()
    if chat is None or chat.type != "group":
        raise HTTPException(status_code=404, detail="Chat not found")
    if _active_member(db, chat_id, me.id) is None:
        raise HTTPException(status_code=403, detail="Not a member")
    new_u = db.query(GameHubUser).filter(GameHubUser.id == body.user_id).first()
    if new_u is None:
        raise HTTPException(status_code=404, detail="User not found")
    now = datetime.now(timezone.utc)
    m = (
        db.query(MessengerChatMember)
        .filter(MessengerChatMember.chat_id == chat_id, MessengerChatMember.user_id == body.user_id)
        .first()
    )
    if m is None:
        db.add(MessengerChatMember(chat_id=chat_id, user_id=body.user_id, joined_at=now))
    else:
        m.left_at = None
        m.joined_at = now
    db.commit()
    await push_to_users(_chat_member_ids(db, chat_id), {"type": "chat.updated", "chat_id": chat_id})
    return {"status": "ok"}


@router.post("/chats/{chat_id}/leave")
async def leave_chat(
    chat_id: int,
    db: Session = Depends(get_db),
    me: GameHubUser = Depends(get_messenger_user),
) -> dict:
    m = (
        db.query(MessengerChatMember)
        .filter(MessengerChatMember.chat_id == chat_id, MessengerChatMember.user_id == me.id)
        .first()
    )
    if m is None:
        raise HTTPException(status_code=404, detail="Not a member")
    m.left_at = datetime.now(timezone.utc)
    db.commit()
    return {"status": "ok"}


# --- messages ---


def _alloc_seq(db: Session, chat_id: int) -> int:
    c = db.query(MessengerChat).filter(MessengerChat.id == chat_id).with_for_update().one()
    c.next_seq = int(c.next_seq or 0) + 1
    seq = int(c.next_seq)
    db.flush()
    return seq


class SendMessageBody(BaseModel):
    text: str = Field(min_length=1, max_length=8000)


@router.get("/chats/{chat_id}/messages")
async def get_messages(
    chat_id: int,
    before: int | None = Query(default=None),
    limit: int = Query(default=40, ge=1, le=100),
    db: Session = Depends(get_db),
    me: GameHubUser = Depends(get_messenger_user),
) -> dict:
    if _active_member(db, chat_id, me.id) is None:
        raise HTTPException(status_code=403, detail="Not a member")
    q = db.query(MessengerMessage).filter(
        MessengerMessage.chat_id == chat_id,
        MessengerMessage.deleted_at.is_(None),
    )
    if before:
        q = q.filter(MessengerMessage.id < before)
    rows = q.order_by(MessengerMessage.id.desc()).limit(limit).all()
    rows = list(reversed(rows))
    users = {u.id: u.username for u in db.query(GameHubUser).filter(GameHubUser.id.in_({m.sender_id for m in rows})).all()}
    return {
        "messages": [
            {
                "id": m.id,
                "seq": int(m.seq),
                "sender_id": m.sender_id,
                "sender_username": users.get(m.sender_id, "?"),
                "kind": m.kind,
                "body": m.body,
                "created_at": m.created_at.isoformat(),
            }
            for m in rows
        ]
    }


@router.post("/chats/{chat_id}/messages")
async def send_message(
    chat_id: int,
    body: SendMessageBody,
    db: Session = Depends(get_db),
    me: GameHubUser = Depends(get_messenger_user),
) -> dict:
    if _active_member(db, chat_id, me.id) is None:
        raise HTTPException(status_code=403, detail="Not a member")
    seq = _alloc_seq(db, chat_id)
    text = body.text.strip()
    msg = MessengerMessage(
        chat_id=chat_id,
        seq=seq,
        sender_id=me.id,
        kind="text",
        body=text,
    )
    db.add(msg)
    now = datetime.now(timezone.utc)
    chat = db.query(MessengerChat).filter(MessengerChat.id == chat_id).first()
    if chat:
        chat.last_message_at = now
        chat.last_message_preview = text[:240]
        chat.updated_at = now
    mids = _chat_member_ids(db, chat_id)
    for uid in mids:
        if uid != me.id:
            mem = (
                db.query(MessengerChatMember)
                .filter(MessengerChatMember.chat_id == chat_id, MessengerChatMember.user_id == uid)
                .first()
            )
            if mem and mem.left_at is None:
                mem.unread_count = int(mem.unread_count or 0) + 1
    db.commit()
    db.refresh(msg)
    payload = {
        "type": "message.new",
        "chat_id": chat_id,
        "message": {
            "id": msg.id,
            "seq": int(msg.seq),
            "sender_id": me.id,
            "sender_username": me.username,
            "kind": msg.kind,
            "body": msg.body,
            "created_at": msg.created_at.isoformat(),
        },
    }
    await push_to_users(mids, payload)
    return {"message": payload["message"]}


@router.post("/chats/{chat_id}/read")
async def mark_read(
    chat_id: int,
    db: Session = Depends(get_db),
    me: GameHubUser = Depends(get_messenger_user),
) -> dict:
    mem = _active_member(db, chat_id, me.id)
    if mem is None:
        raise HTTPException(status_code=403, detail="Not a member")
    last = (
        db.query(func.max(MessengerMessage.seq))
        .filter(MessengerMessage.chat_id == chat_id, MessengerMessage.deleted_at.is_(None))
        .scalar()
    )
    mem.last_read_seq = int(last or 0)
    mem.unread_count = 0
    db.commit()
    return {"status": "ok"}


@router.delete("/messages/{message_id}")
async def delete_message(
    message_id: int,
    db: Session = Depends(get_db),
    me: GameHubUser = Depends(get_messenger_user),
) -> dict:
    m = db.query(MessengerMessage).filter(MessengerMessage.id == message_id).first()
    if m is None:
        raise HTTPException(status_code=404, detail="Not found")
    if m.sender_id != me.id:
        raise HTTPException(status_code=403, detail="Not author")
    if _active_member(db, m.chat_id, me.id) is None:
        raise HTTPException(status_code=403, detail="Not a member")
    m.deleted_at = datetime.now(timezone.utc)
    db.commit()
    await push_to_users(_chat_member_ids(db, m.chat_id), {"type": "message.deleted", "chat_id": m.chat_id, "message_id": m.id})
    return {"status": "ok"}


@router.get("/unread-summary")
async def unread_summary(db: Session = Depends(get_db), me: GameHubUser = Depends(get_messenger_user)) -> dict:
    n = (
        db.query(func.count())
        .select_from(MessengerChatMember)
        .filter(
            MessengerChatMember.user_id == me.id,
            MessengerChatMember.left_at.is_(None),
            MessengerChatMember.unread_count > 0,
        )
        .scalar()
    )
    return {"chats_with_unread": int(n or 0)}


# --- diamonds ---


class TransferDiamondsBody(BaseModel):
    chat_id: int = Field(ge=1)
    to_user_id: int = Field(ge=1)
    amount: int = Field(ge=3, description="Minimum 3 diamonds to recipient")
    idempotency_key: str | None = Field(default=None, max_length=128)


@router.post("/transfer-diamonds")
async def transfer_diamonds(
    body: TransferDiamondsBody,
    request: Request,
    db: Session = Depends(get_db),
    me: GameHubUser = Depends(get_messenger_user),
) -> dict:
    if body.to_user_id == me.id:
        raise HTTPException(status_code=400, detail={"code": "invalid_recipient"})
    if _active_member(db, body.chat_id, me.id) is None:
        raise HTTPException(status_code=403, detail={"code": "not_a_member"})
    if _active_member(db, body.chat_id, body.to_user_id) is None:
        raise HTTPException(status_code=400, detail={"code": "recipient_not_in_chat"})
    recipient = db.query(GameHubUser).filter(GameHubUser.id == body.to_user_id).first()
    if recipient is None:
        raise HTTPException(status_code=404, detail={"code": "recipient_not_found"})

    idem = (body.idempotency_key or "").strip() or None
    if idem:
        existing = db.query(MessengerDiamondLedger).filter(MessengerDiamondLedger.idempotency_key == idem).first()
        if existing is not None:
            msg = db.query(MessengerMessage).filter(MessengerMessage.id == existing.message_id).first()
            if msg is not None:
                s_bal = users_api.get_diamond_balance(me.username)
                r_bal = users_api.get_diamond_balance(recipient.username)
                return {
                    "message": {
                        "id": msg.id,
                        "seq": int(msg.seq),
                        "sender_id": me.id,
                        "sender_username": me.username,
                        "kind": msg.kind,
                        "body": msg.body,
                        "created_at": msg.created_at.isoformat(),
                    },
                    "commission": int(existing.commission),
                    "total_debit": int(existing.total_debit),
                    "idempotent": True,
                    "sender_balance": s_bal,
                    "recipient_balance": r_bal,
                }
    sender_ip = client_ip(request)
    rip = db.query(UserLastIp).filter(UserLastIp.user_id == body.to_user_id).first()
    recipient_ip = rip.ip if rip else ""
    if sender_ip and recipient_ip and sender_ip == recipient_ip:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "same_ip",
            },
        )
    a = int(body.amount)
    f = _commission(a)
    total = a + f
    try:
        names = sorted([me.username, recipient.username])
        locked: dict[str, GameHubUser] = {}
        for name in names:
            u = db.query(GameHubUser).filter(GameHubUser.username == name).with_for_update().first()
            if u is None:
                raise HTTPException(status_code=404, detail={"code": "user_not_found"})
            locked[name] = u
        from app.core.gameshub import ensure_gameshub_schema

        sender_u = locked[me.username]
        recipient_u = locked[recipient.username]
        s_other = ensure_gameshub_schema(sender_u.other_data or {})
        r_other = ensure_gameshub_schema(recipient_u.other_data or {})
        s_cur = int(s_other.get("diamonds", 0))
        r_cur = int(r_other.get("diamonds", 0))
        s_new = s_cur - total
        if s_new < 0:
            raise HTTPException(status_code=400, detail={"code": "insufficient_diamonds", "params": {"required": total}})
        r_new = r_cur + a
        s_other["diamonds"] = s_new
        r_other["diamonds"] = r_new
        sender_u.other_data = s_other
        recipient_u.other_data = r_other
        db.flush()
        seq = _alloc_seq(db, body.chat_id)
        meta = json.dumps({"amount": a, "commission": f, "total_debit": total, "to_user_id": body.to_user_id})
        msg = MessengerMessage(
            chat_id=body.chat_id,
            seq=seq,
            sender_id=me.id,
            kind="diamond_transfer",
            body=meta,
        )
        db.add(msg)
        db.flush()
        db.add(
            MessengerDiamondLedger(
                from_user_id=me.id,
                to_user_id=body.to_user_id,
                amount=a,
                commission=f,
                total_debit=total,
                sender_ip=sender_ip or None,
                recipient_ip=recipient_ip or None,
                chat_id=body.chat_id,
                message_id=msg.id,
                idempotency_key=idem,
            )
        )
        now = datetime.now(timezone.utc)
        chat = db.query(MessengerChat).filter(MessengerChat.id == body.chat_id).first()
        if chat:
            chat.last_message_at = now
            chat.last_message_preview = json.dumps({"kind": "diamond_transfer", "amount": a})
            chat.updated_at = now
        mids = _chat_member_ids(db, body.chat_id)
        for uid in mids:
            if uid != me.id:
                mem = (
                    db.query(MessengerChatMember)
                    .filter(MessengerChatMember.chat_id == body.chat_id, MessengerChatMember.user_id == uid)
                    .first()
                )
                if mem and mem.left_at is None:
                    mem.unread_count = int(mem.unread_count or 0) + 1
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail={"code": "transfer_failed"})
    db.refresh(msg)
    sync_diamonds_to_sessions(me.username, s_new)
    sync_diamonds_to_sessions(recipient.username, r_new)
    payload = {
        "type": "message.new",
        "chat_id": body.chat_id,
        "message": {
            "id": msg.id,
            "seq": int(msg.seq),
            "sender_id": me.id,
            "sender_username": me.username,
            "kind": msg.kind,
            "body": msg.body,
            "created_at": msg.created_at.isoformat(),
        },
        "diamond_credit": {
            "user_id": body.to_user_id,
            "amount": a,
            "balance": r_new,
        },
    }
    await push_to_users(mids, payload)
    return {"message": payload["message"], "commission": f, "total_debit": total}
