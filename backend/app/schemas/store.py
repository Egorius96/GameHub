from pydantic import BaseModel


class BuySuperpowerRequest(BaseModel):
    superpower: str


class UpgradeCarResponse(BaseModel):
    car_level: int
    diamonds: int
