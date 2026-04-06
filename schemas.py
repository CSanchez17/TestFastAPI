from datetime import date

from pydantic import BaseModel, Field, ConfigDict
from fastapi_users import schemas as fastapi_users_schemas


class UserRead(fastapi_users_schemas.BaseUser[int]):
    username: str
    is_host: bool


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
    start_date: date
    end_date: date


class BookingStatusUpdate(BaseModel):
    status: str = Field(..., pattern="^(confirmed|cancelled)$")


class BookingRead(BaseModel):
    booking_id: int = Field(alias="id")
    room_id: int
    guest_id: int
    start_date: date
    end_date: date
    status: str
    booked_price_per_night: float

    model_config = ConfigDict(from_attributes=True)


class DashboardBookingRead(BaseModel):
    booking_id: int = Field(alias="id")
    room_id: int
    room_title: str
    guest_id: int
    guest_username: str
    start_date: date
    end_date: date
    status: str
    booked_price_per_night: float


class HostDashboardRead(BaseModel):
    total_rooms: int
    total_bookings: int
    active_bookings: int
    total_revenue_confirmed: float
    bookings: list[DashboardBookingRead]


class GuestDashboardRead(BaseModel):
    total_bookings: int
    active_bookings: int
    total_spent_confirmed: float
    bookings: list[DashboardBookingRead]
