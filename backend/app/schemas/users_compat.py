from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class UserDataBase(BaseModel):
    username: Optional[str] = None
    password: Optional[str] = None
    project: Optional[str] = None
    other_data: Optional[Dict[str, Any]] = None


class UserDataCreate(UserDataBase):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=200)
    project: str = Field(min_length=1, max_length=64)


class UserDataUpdate(UserDataBase):
    pass


class UserData(UserDataBase):
    id: int


class UserAuth(BaseModel):
    username: str
    password: str


class UpdateRequest(BaseModel):
    user_auth: UserAuth
    user_update: UserDataUpdate


class ProjectUserResponse(BaseModel):
    username: str
    other_data: Optional[Dict[str, Any]] = None


class ProjectUsersListResponse(BaseModel):
    users: List[ProjectUserResponse]

