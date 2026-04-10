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


class LocationBase(BaseModel):
    address_line: str
    city: str
    country: str
    postal_code: str


class LocationCreate(LocationBase):
    pass


class LocationUpdate(BaseModel):
    address_line: str | None = None
    city: str | None = None
    country: str | None = None
    postal_code: str | None = None


class LocationRead(LocationBase):
    location_id: int = Field(alias="id")

    model_config = ConfigDict(from_attributes=True)


class RoomBase(BaseModel):
    title: str
    description: str
    price_per_night: float = Field(..., gt=0)
    is_available: bool = True


class RoomCreate(RoomBase):
    location: LocationCreate


class RoomUpdate(BaseModel):
    title: str | None = None
    location: LocationUpdate | None = None
    description: str | None = None
    price_per_night: float | None = Field(default=None, gt=0)
    is_available: bool | None = None


class RoomRead(RoomBase):
    room_id: int = Field(alias="id")
    location: LocationRead
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


class ConciergeRequest(BaseModel):
    query: str = Field(..., min_length=5)
    max_results: int = Field(default=3, ge=1, le=10)
    language: str = Field(default="en", min_length=2, max_length=5, description="Browser language (ISO 639-1)")
    premium_i18n: bool = Field(default=False, description="Enable translated responses in query language")


class ConciergeRecommendation(BaseModel):
    room_id: int
    title: str
    description: str
    price_per_night: float
    city: str
    country: str
    reason: str


class ConciergeResponse(BaseModel):
    query: str
    extracted_preferences: dict[str, str | float | bool | None]
    assistant_message: str
    recommendations: list[ConciergeRecommendation]
    suggested_queries: list[str] = []
    detected_language: str = "en"


class UserSettingsRead(BaseModel):
    premium_i18n: bool = False

    model_config = ConfigDict(from_attributes=True)


class UserSettingsUpdate(BaseModel):
    premium_i18n: bool | None = None
