from datetime import date
from sqlalchemy import Boolean, Date, Float, ForeignKey, UniqueConstraint
from fastapi_users.db import SQLAlchemyBaseUserTable
from sqlalchemy.orm import Mapped, mapped_column, relationship
from database import Base
from typing import List

class Location(Base):
    __tablename__ = "locations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    address_line: Mapped[str]
    city: Mapped[str]
    country: Mapped[str]
    postal_code: Mapped[str]

    rooms: Mapped[List["Room"]] = relationship(back_populates="location")

    @property
    def rooms_count(self) -> int:
        return len(self.rooms)

    @property
    def full_address(self) -> str:
        return f"{self.address_line}, {self.postal_code} {self.city}, {self.country}"

    def __str__(self) -> str:
        return self.full_address


class Country(Base):
    __tablename__ = "countries"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(unique=True, index=True)

    cities: Mapped[List["City"]] = relationship(
        back_populates="country", cascade="all, delete-orphan"
    )

    def __str__(self) -> str:
        return self.name


class City(Base):
    __tablename__ = "cities"
    __table_args__ = (
        UniqueConstraint("country_id", "name", name="uq_city_country_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(index=True)
    country_id: Mapped[int] = mapped_column(ForeignKey("countries.id"), nullable=False)

    country: Mapped["Country"] = relationship(back_populates="cities")

    @property
    def country_name(self) -> str:
        return self.country.name if self.country else "-"

    def __str__(self) -> str:
        return f"{self.name}, {self.country_name}"


class Room(Base):
    __tablename__ = "rooms"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str]
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), nullable=False)
    description: Mapped[str]
    price_per_night: Mapped[float] = mapped_column(Float)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    location: Mapped["Location"] = relationship(back_populates="rooms")
    owner: Mapped["User"] = relationship(back_populates="rooms")
    bookings: Mapped[List["Booking"]] = relationship(
        back_populates="room", cascade="all, delete-orphan"
    )

    @property
    def bookings_count(self) -> int:
        return len(self.bookings)

    @property
    def owner_username(self) -> str:
        return self.owner.username if self.owner else "-"

    @property
    def full_location(self) -> str:
        return self.location.full_address if self.location else "-"

    @property
    def admin_owner(self):
        return self.owner

    @property
    def admin_location(self):
        return self.location

    @property
    def admin_bookings(self):
        return self.bookings

    def __str__(self) -> str:
        return f"{self.title} (#{self.id})"


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id"), nullable=False)
    guest_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    # Legacy compatibility columns kept for existing DB files.
    check_in: Mapped[date | None] = mapped_column(Date, nullable=True)
    check_out: Mapped[date | None] = mapped_column(Date, nullable=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(default="confirmed", nullable=False)
    booked_price_per_night: Mapped[float] = mapped_column(Float, nullable=False)

    room: Mapped["Room"] = relationship(back_populates="bookings")
    guest: Mapped["User"] = relationship(back_populates="bookings")

    @property
    def room_title(self) -> str:
        return self.room.title if self.room else "-"

    @property
    def guest_username(self) -> str:
        return self.guest.username if self.guest else "-"

    @property
    def total_price(self) -> float:
        nights = max((self.end_date - self.start_date).days, 0)
        return float(self.booked_price_per_night) * nights

    @property
    def admin_room(self):
        return self.room

    @property
    def admin_guest(self):
        return self.guest

    def __str__(self) -> str:
        return f"Booking #{self.id} - {self.status}"


class User(Base, SQLAlchemyBaseUserTable[int]):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(unique=True, index=True)
    is_host: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    email: Mapped[str] = mapped_column(unique=True, index=True)
    hashed_password: Mapped[str]

    rooms: Mapped[List["Room"]] = relationship(back_populates="owner")
    bookings: Mapped[List["Booking"]] = relationship(back_populates="guest")
    settings: Mapped["UserSettings"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan", lazy="selectin",
    )

    @property
    def rooms_count(self) -> int:
        return len(self.rooms)

    @property
    def bookings_count(self) -> int:
        return len(self.bookings)

    @property
    def admin_rooms(self):
        return self.rooms

    @property
    def admin_bookings(self):
        return self.bookings

    def __str__(self) -> str:
        return f"{self.username} (#{self.id})"


class UserSettings(Base):
    """Per-user feature toggles and preferences."""
    __tablename__ = "user_settings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    premium_i18n: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    user: Mapped["User"] = relationship(back_populates="settings")

    def __str__(self) -> str:
        return f"Settings for user #{self.user_id}"