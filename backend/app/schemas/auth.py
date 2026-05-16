from pydantic import BaseModel, Field


class AuthRequest(BaseModel):
    username: str = Field(min_length=1, max_length=20)
    password: str = Field(min_length=1, max_length=50)


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    other_data: dict


class DeleteAccountRequest(BaseModel):
    password: str = Field(min_length=1, max_length=50)
