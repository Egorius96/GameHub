from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import LegacyUser
from app.db.session import get_db
from app.schemas.users_compat import (
    ProjectUserResponse,
    ProjectUsersListResponse,
    UpdateRequest,
    UserAuth,
    UserData,
    UserDataCreate,
)

router = APIRouter(prefix="/users", tags=["users_compat"])


def _authenticate(db: Session, username: str, password: str) -> LegacyUser:
    u = (
        db.query(LegacyUser)
        .filter(LegacyUser.username == username)
        .filter(LegacyUser.password == password)
        .first()
    )
    if u is None:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    return u


def _unique_detail(msg: str) -> str:
    if "username" in msg.lower():
        return "Username already exists"
    return "Unique constraint violation"


@router.post("/", response_model=UserData)
def create_user(payload: UserDataCreate, db: Session = Depends(get_db)) -> UserData:
    try:
        u = LegacyUser(
            username=payload.username,
            password=payload.password,
            project=payload.project,
            other_data=payload.other_data,
        )
        db.add(u)
        db.commit()
        db.refresh(u)
        return UserData(id=u.id, username=u.username, password=u.password, project=u.project, other_data=u.other_data)
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=_unique_detail(str(getattr(e, "orig", e)))) from e


@router.get("/", response_model=List[UserData])
def list_users(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> List[UserData]:
    users = db.query(LegacyUser).offset(skip).limit(limit).all()
    return [UserData(id=u.id, username=u.username, password=u.password, project=u.project, other_data=u.other_data) for u in users]


@router.post("/auth", response_model=UserData)
def auth(payload: UserAuth, db: Session = Depends(get_db)) -> UserData:
    u = _authenticate(db, payload.username, payload.password)
    return UserData(id=u.id, username=u.username, password=u.password, project=u.project, other_data=u.other_data)


@router.put("/update", response_model=UserData)
def update_user(payload: UpdateRequest, db: Session = Depends(get_db)) -> UserData:
    u = _authenticate(db, payload.user_auth.username, payload.user_auth.password)
    try:
        upd = payload.user_update.model_dump(exclude_unset=True)
        for k, v in upd.items():
            setattr(u, k, v)
        db.commit()
        db.refresh(u)
        return UserData(id=u.id, username=u.username, password=u.password, project=u.project, other_data=u.other_data)
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=_unique_detail(str(getattr(e, "orig", e)))) from e


@router.delete("/delete", response_model=dict)
def delete_user(payload: UserAuth, db: Session = Depends(get_db)) -> dict:
    try:
        u = _authenticate(db, payload.username, payload.password)
        db.delete(u)
        db.commit()
        return {"message": "User deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to delete user") from e


@router.post("/get_users_by_project", response_model=ProjectUsersListResponse)
def get_users_by_project(payload: UserAuth, db: Session = Depends(get_db)) -> ProjectUsersListResponse:
    auth_u = _authenticate(db, payload.username, payload.password)
    users = db.query(LegacyUser).filter(LegacyUser.project == auth_u.project).all()
    return ProjectUsersListResponse(
        users=[ProjectUserResponse(username=u.username, other_data=u.other_data) for u in users]
    )

