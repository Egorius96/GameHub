from pydantic import BaseModel
from typing import Optional, Dict, Any, List

class UserDataBase(BaseModel):
    username: Optional[str] = None
    password: Optional[str] = None
    project: Optional[str] = None
    other_data: Optional[Dict[str, Any]] = None

class UserDataCreate(UserDataBase):
    pass

class UserDataUpdate(UserDataBase):
    pass

class UserData(UserDataBase):
    id: int

    class Config:
        from_attributes = True

class UserAuth(BaseModel):
    username: str
    password: str

class ProjectUserResponse(BaseModel):
    username: str
    other_data: Optional[Dict[str, Any]] = None

class ProjectUsersListResponse(BaseModel):
    users: List[ProjectUserResponse] 