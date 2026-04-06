from datetime import date
from sqlalchemy import Boolean, Date, Float, ForeignKey
from fastapi_users.db import SQLAlchemyBaseUserTable
from sqlalchemy.orm import Mapped, mapped_column, relationship
from database import Base
from typing import List

# Rooms represent properties listed by hosts.
class Room(Base):
    __tablename__ = "rooms"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str]
    description: Mapped[str]
    price_per_night: Mapped[float] = mapped_column(Float)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    owner: Mapped["User"] = relationship(back_populates="rooms")
    bookings: Mapped[List["Booking"]] = relationship(
        back_populates="room", cascade="all, delete-orphan"
    )

    @property
    def bookings_count(self) -> int:
        return len(self.bookings)

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

    @property
    def rooms_count(self) -> int:
        return len(self.rooms)

    @property
    def bookings_count(self) -> int:
        return len(self.bookings)

    def __str__(self) -> str:
        return f"{self.username} (#{self.id})"