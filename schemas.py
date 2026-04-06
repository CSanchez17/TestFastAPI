from datetime import date

from pydantic import BaseModel, Field, ConfigDict
from fastapi_users import schemas as fastapi_users_schemas


class UserRead(fastapi_users_schemas.BaseUser[int]):
    username: str


class UserCreate(fastapi_users_schemas.BaseUserCreate):
    username: str


class UserUpdate(fastapi_users_schemas.BaseUserUpdate):
    username: str | None = None


class RoomBase(BaseModel):
    title: str
    description: str
    price_per_night: float = Field(..., gt=0)
    is_available: bool = True


class RoomCreate(RoomBase):
    pass


class RoomUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    price_per_night: float | None = Field(default=None, gt=0)
    is_available: bool | None = None


class RoomRead(RoomBase):
    room_id: int = Field(alias="id")
    owner: UserRead

    model_config = ConfigDict(
        from_attributes=True,
    )


class BookingCreate(BaseModel):
    room_id: int = Field(..., gt=0)
    check_in: date
    check_out: date


class BookingRead(BaseModel):
    booking_id: int = Field(alias="id")
    room_id: int
    guest_id: int
    check_in: date
    check_out: date

    model_config = ConfigDict(from_attributes=True)
