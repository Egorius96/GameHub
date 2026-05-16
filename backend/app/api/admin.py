from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, text

from app.core.config import settings
from app.core.security import decode_access_token_payload
from datetime import date, datetime, timedelta, timezone

from pydantic import BaseModel, Field

from app.db.models import (
    GameHubUser,
    LegacyUser,
    GameLike,
    WarningHistory,
    IncidentAck,
    MessengerChat,
    MessengerChatMember,
    MessengerMessage,
    MessengerDiamondLedger,
)
from app.db.session import get_db
from app.services.ban_state import clear_expired_temp_ban, is_login_blocked, utcnow

router = APIRouter(prefix="/api/admin", tags=["admin"])

# Совпадает с логикой автопометки в likes.py: ≥ столько разных аккаунтов с одного IP за день
IP_INCIDENT_MIN_ACCOUNTS = 4


def _since_date_for_incidents(days: int) -> date:
    return datetime.now(timezone.utc).date() - timedelta(days=int(days) - 1)


def _count_unacked_incidents(db: Session, days: int) -> int:
    since = _since_date_for_incidents(days)
    row = db.execute(
        text(
            """
            WITH inc AS (
                SELECT ip, day
                FROM game_likes
                WHERE day >= :since
                GROUP BY ip, day
                HAVING COUNT(DISTINCT user_id) >= :th
            )
            SELECT COUNT(*)::int AS c
            FROM inc i
            WHERE NOT EXISTS (
                SELECT 1 FROM incident_ack a WHERE a.ip = i.ip AND a.day = i.day
            )
            """
        ),
        {"since": since, "th": IP_INCIDENT_MIN_ACCOUNTS},
    ).fetchone()
    return int(row[0] if row and row[0] is not None else 0)


def _upsert_incident_ack(db: Session, ip: str, day_d: date) -> None:
    now = utcnow()
    row = db.query(IncidentAck).filter(IncidentAck.ip == ip, IncidentAck.day == day_d).first()
    if row:
        row.acked_at = now
    else:
        db.add(IncidentAck(ip=ip, day=day_d, acked_at=now))

TableName = Literal["gamehub_users", "users"]


def _require_admin(authorization: str = Header(default="")) -> None:
    token = authorization.replace("Bearer ", "")
    payload = decode_access_token_payload(token)
    if not payload or payload.get("sub") != "admindb" or payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")


@router.get("/tables")
def tables(_: None = Depends(_require_admin)) -> dict:
    return {"tables": ["gamehub_users", "users"]}


@router.get("/stats")
def stats(
    day: str = Query(default="", description="YYYY-MM-DD, по умолчанию сегодня"),
    _: None = Depends(_require_admin),
    db: Session = Depends(get_db),
) -> dict:
    # day парсим в SQL (минимум логики тут)
    d = day.strip() or None
    if d:
        row = db.execute(text("SELECT day, count FROM request_stats_daily WHERE day = :d"), {"d": d}).fetchone()
        top = db.execute(
            text(
                """
                SELECT method, path, count
                FROM request_stats_path
                WHERE day = :d
                ORDER BY count DESC
                LIMIT 20
                """
            ),
            {"d": d},
        ).fetchall()
        return {
            "day": d,
            "count": int(row.count) if row else 0,
            "top": [{"method": t.method, "path": t.path, "count": int(t.count)} for t in top],
        }
    # today
    row = db.execute(text("SELECT day, count FROM request_stats_daily ORDER BY day DESC LIMIT 1")).fetchone()
    if not row:
        return {"day": None, "count": 0, "top": []}
    top = db.execute(
        text(
            """
            SELECT method, path, count
            FROM request_stats_path
            WHERE day = :d
            ORDER BY count DESC
            LIMIT 20
            """
        ),
        {"d": row.day},
    ).fetchall()
    return {
        "day": str(row.day),
        "count": int(row.count),
        "top": [{"method": t.method, "path": t.path, "count": int(t.count)} for t in top],
    }


def _row_gamehub(u: GameHubUser) -> dict[str, Any]:
    bu = getattr(u, "banned_until", None)
    return {
        "id": u.id,
        "username": u.username,
        "password": u.password,
        "project": u.project,
        "other_data": u.other_data or {},
        "blocked": bool(getattr(u, "blocked", False)),
        "banned_until": bu.isoformat() if bu else None,
        "suspicious": bool(getattr(u, "suspicious", False)),
        "login_count": int(getattr(u, "login_count", 0) or 0),
        "last_active_at": u.last_active_at,
        "warning_count": int(getattr(u, "warning_count", 0) or 0),
        "mod_warning_text": getattr(u, "mod_warning_text", None) or "",
        "created_at": u.created_at,
        "updated_at": u.updated_at,
    }


def _block_user_and_strip_likes(db: Session, u: GameHubUser) -> None:
    u.blocked = True
    u.banned_until = None
    db.query(GameLike).filter(GameLike.user_id == u.id).delete(synchronize_session=False)


class BanTempBody(BaseModel):
    minutes: int = Field(ge=1, le=525600, description="1..525600 (до ~1 года)")


class IncidentKeyBody(BaseModel):
    ip: str = Field(min_length=1, max_length=64)
    day: str = Field(min_length=10, max_length=10, description="YYYY-MM-DD")


class IncidentBulkWarnBody(IncidentKeyBody):
    text: str = Field(min_length=1, max_length=4000)


def _row_legacy(u: LegacyUser) -> dict[str, Any]:
    return {
        "id": u.id,
        "username": u.username,
        "password": u.password,
        "project": u.project,
        "other_data": u.other_data or {},
        "created_at": u.created_at,
        "updated_at": u.updated_at,
    }


@router.get("/gamehub_users")
def list_gamehub_users(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _: None = Depends(_require_admin),
    db: Session = Depends(get_db),
) -> dict:
    rows = db.query(GameHubUser).offset(offset).limit(limit).all()
    return {"rows": [_row_gamehub(r) for r in rows]}


def _dt_iso(v: Any) -> str | None:
    if v is None:
        return None
    if hasattr(v, "isoformat"):
        return v.isoformat()  # type: ignore[no-any-return]
    return str(v)


@router.get("/suspicious/unacked-count")
def suspicious_unacked_count(
    days: int = Query(default=7, ge=1, le=365),
    _: None = Depends(_require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Сколько инцидентов (ip+день) за период без отметки «обработано» — для бейджа в админке."""
    return {"count": _count_unacked_incidents(db, days), "days": days}


@router.get("/suspicious")
def suspicious(
    days: int = Query(default=1, ge=1, le=365),
    _: None = Depends(_require_admin),
    db: Session = Depends(get_db),
) -> dict:
    since = _since_date_for_incidents(int(days))
    keys = db.execute(
        text(
            """
            SELECT ip, day, COUNT(*)::bigint AS votes, COUNT(DISTINCT user_id)::bigint AS accounts
            FROM game_likes
            WHERE day >= :since
            GROUP BY ip, day
            HAVING COUNT(DISTINCT user_id) >= :th
            ORDER BY day DESC, ip ASC
            LIMIT 150
            """
        ),
        {"since": since, "th": IP_INCIDENT_MIN_ACCOUNTS},
    ).fetchall()

    incidents: list[dict[str, Any]] = []
    for r in keys:
        ip_s = str(r.ip)
        day_v = r.day
        acc_rows = db.execute(
            text(
                """
                SELECT gl.user_id, gl.username,
                    COUNT(*)::int AS votes_in_incident,
                    MIN(gl.created_at) AS first_vote_at,
                    MAX(gl.created_at) AS last_vote_at,
                    u.created_at AS user_created_at,
                    u.last_active_at AS user_last_active_at
                FROM game_likes gl
                LEFT JOIN gamehub_users u ON u.id = gl.user_id
                WHERE gl.ip = :ip AND gl.day = :day
                GROUP BY gl.user_id, gl.username, u.created_at, u.last_active_at
                ORDER BY last_vote_at DESC
                """
            ),
            {"ip": ip_s, "day": day_v},
        ).mappings().all()
        accounts = [
            {
                "user_id": int(ar["user_id"]),
                "username": str(ar["username"]),
                "votes_in_incident": int(ar["votes_in_incident"] or 0),
                "first_vote_at": _dt_iso(ar["first_vote_at"]),
                "last_vote_at": _dt_iso(ar["last_vote_at"]),
                "user_created_at": _dt_iso(ar["user_created_at"]),
                "user_last_active_at": _dt_iso(ar["user_last_active_at"]),
            }
            for ar in acc_rows
        ]
        acked = (
            db.query(IncidentAck)
            .filter(IncidentAck.ip == ip_s, IncidentAck.day == day_v)
            .first()
            is not None
        )
        incidents.append(
            {
                "id": f"{ip_s}|{day_v}",
                "ip": ip_s,
                "day": str(day_v),
                "votes": int(r.votes),
                "distinct_accounts": int(r.accounts),
                "accounts": accounts,
                "acked": acked,
            }
        )

    sus = db.query(GameHubUser).filter(GameHubUser.suspicious == True).limit(500).all()  # noqa: E712
    return {
        "since": str(since),
        "incident_threshold_accounts": IP_INCIDENT_MIN_ACCOUNTS,
        "incidents": incidents,
        "users": [_row_gamehub(u) for u in sus],
    }


@router.post("/incident/bulk_warn")
def incident_bulk_warn(
    payload: IncidentBulkWarnBody,
    _: None = Depends(_require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Один и тот же текст предупреждения всем аккаунтам, которые голосовали с этого IP в указанный день."""
    ip = payload.ip.strip()
    try:
        day_d = date.fromisoformat(payload.day.strip()[:10])
    except ValueError:
        raise HTTPException(status_code=400, detail="bad day format, use YYYY-MM-DD")
    text_msg = payload.text.strip()
    rows = db.execute(
        text("SELECT DISTINCT user_id FROM game_likes WHERE ip = :ip AND day = :day"),
        {"ip": ip, "day": day_d},
    ).fetchall()
    user_ids = [int(r[0]) for r in rows if r[0] is not None]
    if not user_ids:
        raise HTTPException(status_code=404, detail="no votes for this ip/day")
    warned = 0
    skipped_blocked = 0
    skipped_catalog = 0
    for uid in user_ids:
        u = db.query(GameHubUser).filter(GameHubUser.id == uid).first()
        if u is None:
            continue
        if u.username == settings.catalog_username:
            skipped_catalog += 1
            continue
        clear_expired_temp_ban(db, u)
        db.refresh(u)
        if is_login_blocked(u):
            skipped_blocked += 1
            continue
        u.mod_warning_text = text_msg
        show_until = int(getattr(u, "login_count", 0) or 0) + 9999
        db.add(WarningHistory(user_id=u.id, text=text_msg, show_until_login_count=show_until))
        warned += 1
    _upsert_incident_ack(db, ip, day_d)
    db.commit()
    return {
        "ok": True,
        "accounts_in_incident": len(user_ids),
        "warned": warned,
        "skipped_blocked": skipped_blocked,
        "skipped_catalog": skipped_catalog,
    }


@router.post("/incident/bulk_warning_increment")
def incident_bulk_warning_increment(
    payload: IncidentKeyBody,
    _: None = Depends(_require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """+1 к warning_count каждому участнику инцидента (ip+день); при 3 — бан как по одиночному эндпоинту."""
    ip = payload.ip.strip()
    try:
        day_d = date.fromisoformat(payload.day.strip()[:10])
    except ValueError:
        raise HTTPException(status_code=400, detail="bad day format, use YYYY-MM-DD")
    rows = db.execute(
        text("SELECT DISTINCT user_id FROM game_likes WHERE ip = :ip AND day = :day"),
        {"ip": ip, "day": day_d},
    ).fetchall()
    user_ids = [int(r[0]) for r in rows if r[0] is not None]
    if not user_ids:
        raise HTTPException(status_code=404, detail="no votes for this ip/day")
    incremented = 0
    skipped_blocked = 0
    skipped_catalog = 0
    skipped_already_max = 0
    blocked_after = 0
    for uid in user_ids:
        u = db.query(GameHubUser).filter(GameHubUser.id == uid).first()
        if u is None:
            continue
        if u.username == settings.catalog_username:
            skipped_catalog += 1
            continue
        clear_expired_temp_ban(db, u)
        db.refresh(u)
        if is_login_blocked(u):
            skipped_blocked += 1
            continue
        cur = int(getattr(u, "warning_count", 0) or 0)
        if cur >= 3:
            skipped_already_max += 1
            continue
        was_blocked = bool(u.blocked)
        u.warning_count = min(3, cur + 1)
        if u.warning_count >= 3:
            _block_user_and_strip_likes(db, u)
            if not was_blocked and u.blocked:
                blocked_after += 1
        incremented += 1
    _upsert_incident_ack(db, ip, day_d)
    db.commit()
    return {
        "ok": True,
        "accounts_in_incident": len(user_ids),
        "incremented": incremented,
        "skipped_blocked": skipped_blocked,
        "skipped_catalog": skipped_catalog,
        "skipped_already_max": skipped_already_max,
        "newly_perma_blocked": blocked_after,
    }


@router.post("/incident/ack")
def incident_ack(
    payload: IncidentKeyBody,
    _: None = Depends(_require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Отметить инцидент (ip+день) как обработанный без массовых действий — уменьшает счётчик на главной админке."""
    ip = payload.ip.strip()
    try:
        day_d = date.fromisoformat(payload.day.strip()[:10])
    except ValueError:
        raise HTTPException(status_code=400, detail="bad day format, use YYYY-MM-DD")
    row = db.execute(
        text("SELECT 1 FROM game_likes WHERE ip = :ip AND day = :day LIMIT 1"),
        {"ip": ip, "day": day_d},
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="no votes for this ip/day")
    _upsert_incident_ack(db, ip, day_d)
    db.commit()
    return {"ok": True}


@router.post("/warn/{user_id}")
def warn_user(
    user_id: int,
    payload: dict[str, Any],
    _: None = Depends(_require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Текст предупреждения для баннера в меню + запись в историю (уровень предупреждений задаётся отдельно)."""
    text_msg = str(payload.get("text") or "").strip()
    if not text_msg:
        raise HTTPException(status_code=400, detail="text required")
    u = db.query(GameHubUser).filter(GameHubUser.id == user_id).first()
    if u is None:
        raise HTTPException(status_code=404, detail="Not found")
    clear_expired_temp_ban(db, u)
    db.refresh(u)
    if is_login_blocked(u):
        raise HTTPException(status_code=400, detail="User already blocked")
    u.mod_warning_text = text_msg
    show_until = int(getattr(u, "login_count", 0) or 0) + 9999
    wh = WarningHistory(user_id=u.id, text=text_msg, show_until_login_count=show_until)
    db.add(wh)
    db.commit()
    return {"ok": True}


@router.post("/warning_increment/{user_id}")
def warning_increment(
    user_id: int,
    _: None = Depends(_require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Вручную +1 к счётчику предупреждений; при достижении 3 — автоматический бан и удаление лайков."""
    u = db.query(GameHubUser).filter(GameHubUser.id == user_id).first()
    if u is None:
        raise HTTPException(status_code=404, detail="Not found")
    clear_expired_temp_ban(db, u)
    db.refresh(u)
    if is_login_blocked(u):
        raise HTTPException(status_code=400, detail="User already blocked")
    cur = int(getattr(u, "warning_count", 0) or 0)
    if cur >= 3:
        raise HTTPException(status_code=400, detail="warning_count already at max")
    u.warning_count = min(3, cur + 1)
    if u.warning_count >= 3:
        _block_user_and_strip_likes(db, u)
    db.commit()
    return {"ok": True, "warning_count": int(u.warning_count), "blocked": bool(u.blocked)}


@router.get("/warnings/{user_id}")
def list_warnings(
    user_id: int,
    _: None = Depends(_require_admin),
    db: Session = Depends(get_db),
) -> dict:
    rows = (
        db.query(WarningHistory)
        .filter(WarningHistory.user_id == user_id)
        .order_by(WarningHistory.created_at.desc())
        .limit(100)
        .all()
    )
    return {
        "rows": [
            {"id": w.id, "text": w.text, "created_at": w.created_at.isoformat(), "show_until_login_count": w.show_until_login_count}
            for w in rows
        ]
    }


@router.post("/block/{user_id}")
def block_user(
    user_id: int,
    _: None = Depends(_require_admin),
    db: Session = Depends(get_db),
) -> dict:
    u = db.query(GameHubUser).filter(GameHubUser.id == user_id).first()
    if u is None:
        raise HTTPException(status_code=404, detail="Not found")
    _block_user_and_strip_likes(db, u)
    db.commit()
    return {"ok": True}


@router.post("/ban_temp/{user_id}")
def ban_temp(
    user_id: int,
    payload: BanTempBody,
    _: None = Depends(_require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Временный бан: blocked + banned_until; по истечении пользователь войдёт сам."""
    u = db.query(GameHubUser).filter(GameHubUser.id == user_id).first()
    if u is None:
        raise HTTPException(status_code=404, detail="Not found")
    clear_expired_temp_ban(db, u)
    db.refresh(u)
    if is_login_blocked(u):
        raise HTTPException(status_code=400, detail="User already has active ban")
    until = utcnow() + timedelta(minutes=int(payload.minutes))
    u.blocked = True
    u.banned_until = until
    db.commit()
    return {"ok": True, "banned_until": until.isoformat()}


@router.post("/unban/{user_id}")
def unban_user(
    user_id: int,
    _: None = Depends(_require_admin),
    db: Session = Depends(get_db),
) -> dict:
    u = db.query(GameHubUser).filter(GameHubUser.id == user_id).first()
    if u is None:
        raise HTTPException(status_code=404, detail="Not found")
    u.blocked = False
    u.banned_until = None
    db.commit()
    return {"ok": True}


@router.post("/purge_ip")
def purge_ip(
    payload: dict[str, Any],
    _: None = Depends(_require_admin),
    db: Session = Depends(get_db),
) -> dict:
    ip = str(payload.get("ip") or "").strip()
    period = str(payload.get("period") or "").strip()
    if not ip:
        raise HTTPException(status_code=400, detail="ip required")
    days_map = {
        "1d": 1,
        "3d": 3,
        "1w": 7,
        "1m": 30,
        "2m": 60,
        "3m": 90,
        "1y": 365,
    }
    if period not in days_map:
        raise HTTPException(status_code=400, detail="bad period")
    since = datetime.now(timezone.utc).date() - timedelta(days=days_map[period] - 1)
    n = db.query(GameLike).filter(GameLike.ip == ip).filter(GameLike.day >= since).delete(synchronize_session=False)
    db.commit()
    return {"ok": True, "deleted": int(n or 0), "since": str(since)}


@router.post("/gamehub_users")
def create_gamehub_user(
    payload: dict[str, Any],
    _: None = Depends(_require_admin),
    db: Session = Depends(get_db),
) -> dict:
    username = str(payload.get("username") or "").strip()
    password = str(payload.get("password") or "")
    project = str(payload.get("project") or "GamesHub")
    other_data = payload.get("other_data") if isinstance(payload.get("other_data"), dict) else {}
    if not username or not password:
        raise HTTPException(status_code=400, detail="username and password required")
    u = GameHubUser(username=username, password=password, project=project, other_data=other_data)
    db.add(u)
    db.commit()
    db.refresh(u)
    return {"row": _row_gamehub(u)}


@router.put("/gamehub_users/{user_id}")
def update_gamehub_user(
    user_id: int,
    payload: dict[str, Any],
    _: None = Depends(_require_admin),
    db: Session = Depends(get_db),
) -> dict:
    u = db.query(GameHubUser).filter(GameHubUser.id == user_id).first()
    if u is None:
        raise HTTPException(status_code=404, detail="Not found")
    for k in ("username", "password", "project"):
        if k in payload and payload[k] is not None:
            setattr(u, k, str(payload[k]))
    if "other_data" in payload and isinstance(payload.get("other_data"), dict):
        u.other_data = payload["other_data"]
    db.commit()
    db.refresh(u)
    return {"row": _row_gamehub(u)}


@router.delete("/gamehub_users/{user_id}")
def delete_gamehub_user(
    user_id: int,
    _: None = Depends(_require_admin),
    db: Session = Depends(get_db),
) -> dict:
    u = db.query(GameHubUser).filter(GameHubUser.id == user_id).first()
    if u is None:
        raise HTTPException(status_code=404, detail="Not found")
    if u.username == settings.catalog_username:
        raise HTTPException(status_code=400, detail="Cannot delete system catalog user")
    db.query(GameLike).filter(GameLike.user_id == user_id).delete(synchronize_session=False)
    db.delete(u)
    db.commit()
    return {"ok": True}


@router.get("/users")
def list_legacy_users(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _: None = Depends(_require_admin),
    db: Session = Depends(get_db),
) -> dict:
    rows = db.query(LegacyUser).offset(offset).limit(limit).all()
    return {"rows": [_row_legacy(r) for r in rows]}


@router.post("/users")
def create_legacy_user(
    payload: dict[str, Any],
    _: None = Depends(_require_admin),
    db: Session = Depends(get_db),
) -> dict:
    username = str(payload.get("username") or "").strip()
    password = str(payload.get("password") or "")
    project = str(payload.get("project") or "")
    other_data = payload.get("other_data") if isinstance(payload.get("other_data"), dict) else {}
    if not username or not password or not project:
        raise HTTPException(status_code=400, detail="username, password, project required")
    u = LegacyUser(username=username, password=password, project=project, other_data=other_data)
    db.add(u)
    db.commit()
    db.refresh(u)
    return {"row": _row_legacy(u)}


@router.put("/users/{user_id}")
def update_legacy_user(
    user_id: int,
    payload: dict[str, Any],
    _: None = Depends(_require_admin),
    db: Session = Depends(get_db),
) -> dict:
    u = db.query(LegacyUser).filter(LegacyUser.id == user_id).first()
    if u is None:
        raise HTTPException(status_code=404, detail="Not found")
    for k in ("username", "password", "project"):
        if k in payload and payload[k] is not None:
            setattr(u, k, str(payload[k]))
    if "other_data" in payload and isinstance(payload.get("other_data"), dict):
        u.other_data = payload["other_data"]
    db.commit()
    db.refresh(u)
    return {"row": _row_legacy(u)}


@router.delete("/users/{user_id}")
def delete_legacy_user(
    user_id: int,
    _: None = Depends(_require_admin),
    db: Session = Depends(get_db),
) -> dict:
    u = db.query(LegacyUser).filter(LegacyUser.id == user_id).first()
    if u is None:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(u)
    db.commit()
    return {"ok": True}


# --- messenger moderation ---


@router.get("/messenger/chats")
def admin_messenger_chats(
    username: str = Query("", min_length=0, max_length=64),
    limit: int = Query(default=40, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: None = Depends(_require_admin),
    db: Session = Depends(get_db),
) -> dict:
    u = db.query(GameHubUser).filter(GameHubUser.username == username.strip()).first()
    if u is None:
        return {"chats": []}
    q = (
        db.query(MessengerChat)
        .join(MessengerChatMember, MessengerChatMember.chat_id == MessengerChat.id)
        .filter(MessengerChatMember.user_id == u.id)
        .order_by(MessengerChat.id.desc())
        .offset(offset)
        .limit(limit)
    )
    out = []
    for c in q.all():
        out.append(
            {
                "id": c.id,
                "type": c.type,
                "title": c.title,
                "dm_peer_key": c.dm_peer_key,
                "last_message_at": c.last_message_at.isoformat() if c.last_message_at else None,
                "last_message_preview": c.last_message_preview,
            }
        )
    return {"chats": out}


@router.get("/messenger/chats/{chat_id}/messages")
def admin_messenger_messages(
    chat_id: int,
    limit: int = Query(default=80, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _: None = Depends(_require_admin),
    db: Session = Depends(get_db),
) -> dict:
    rows = (
        db.query(MessengerMessage)
        .filter(MessengerMessage.chat_id == chat_id)
        .order_by(MessengerMessage.id.asc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    senders = {u.id: u.username for u in db.query(GameHubUser).filter(GameHubUser.id.in_({m.sender_id for m in rows})).all()}
    return {
        "messages": [
            {
                "id": m.id,
                "seq": int(m.seq),
                "sender_id": m.sender_id,
                "sender_username": senders.get(m.sender_id, "?"),
                "kind": m.kind,
                "body": m.body,
                "created_at": m.created_at.isoformat(),
                "deleted_at": m.deleted_at.isoformat() if m.deleted_at else None,
            }
            for m in rows
        ]
    }


@router.get("/messenger/diamond-ledger")
def admin_messenger_diamond_ledger(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: None = Depends(_require_admin),
    db: Session = Depends(get_db),
) -> dict:
    total_row = db.query(func.coalesce(func.sum(MessengerDiamondLedger.commission), 0)).scalar()
    rows = (
        db.query(MessengerDiamondLedger)
        .order_by(MessengerDiamondLedger.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    ids: set[int] = set()
    for r in rows:
        ids.add(r.from_user_id)
        ids.add(r.to_user_id)
    users = db.query(GameHubUser).filter(GameHubUser.id.in_(ids)).all() if ids else []
    unames = {u.id: u.username for u in users}
    return {
        "total_commission_all_time": int(total_row or 0),
        "entries": [
            {
                "id": r.id,
                "created_at": r.created_at.isoformat(),
                "from_user_id": r.from_user_id,
                "from_username": unames.get(r.from_user_id, "?"),
                "to_user_id": r.to_user_id,
                "to_username": unames.get(r.to_user_id, "?"),
                "amount": r.amount,
                "commission": r.commission,
                "total_debit": r.total_debit,
                "sender_ip": r.sender_ip,
                "recipient_ip": r.recipient_ip,
                "chat_id": r.chat_id,
            }
            for r in rows
        ],
    }
