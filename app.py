from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Path, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from database import AsyncSessionLocal, init_db
from models import Booking, Room, User
from schemas import (
    BookingCreate,
    BookingRead,
    RoomCreate,
    RoomRead,
    RoomUpdate,
    UserCreate,
    UserRead,
    UserUpdate,
)
from users import auth_backend, current_active_user, fastapi_users


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


fastapi_app = FastAPI(lifespan=lifespan)

# Auth and users
fastapi_app.include_router(
    fastapi_users.get_auth_router(auth_backend),
    prefix="/auth/jwt",
    tags=["auth"],
)
fastapi_app.include_router(
    fastapi_users.get_register_router(UserRead, UserCreate),
    prefix="/auth",
    tags=["auth"],
)
fastapi_app.include_router(
    fastapi_users.get_users_router(UserRead, UserUpdate),
    prefix="/users",
    tags=["users"],
)


@fastapi_app.get("/all-users", response_model=list[UserRead], tags=["users"])
async def get_all_users(current_user: User = Depends(current_active_user)):
    """Return all registered users (requires authentication)."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).order_by(User.id))
        users = result.scalars().all()
        return [UserRead.model_validate(user) for user in users]


@fastapi_app.get("/rooms", response_model=list[RoomRead], tags=["rooms"])
async def list_available_rooms():
    """Public endpoint: list rooms that are currently available."""
    async with AsyncSessionLocal() as session:
        stmt = (
            select(Room)
            .options(selectinload(Room.owner))
            .where(Room.is_available.is_(True))
            .order_by(Room.id)
        )
        result = await session.execute(stmt)
        rooms = result.scalars().all()
        return [RoomRead.model_validate(room) for room in rooms]


@fastapi_app.get("/rooms/{room_id}", response_model=RoomRead, tags=["rooms"])
async def get_room(room_id: int = Path(..., description="ID of the room", gt=0)):
    """Public endpoint: get room details by ID."""
    async with AsyncSessionLocal() as session:
        stmt = select(Room).options(selectinload(Room.owner)).where(Room.id == room_id)
        result = await session.execute(stmt)
        room = result.scalar_one_or_none()

        if room is None:
            raise HTTPException(status_code=404, detail="Room not found")

        return RoomRead.model_validate(room)


@fastapi_app.post("/rooms", response_model=RoomRead, tags=["rooms"])
async def create_room(
    room_in: RoomCreate,
    current_user: User = Depends(current_active_user),
):
    """Host endpoint: create a room owned by the authenticated user."""
    async with AsyncSessionLocal() as session:
        new_room = Room(
            title=room_in.title,
            description=room_in.description,
            price_per_night=room_in.price_per_night,
            is_available=room_in.is_available,
            owner_id=current_user.id,
        )
        session.add(new_room)
        await session.commit()

        stmt = select(Room).options(selectinload(Room.owner)).where(Room.id == new_room.id)
        room = (await session.execute(stmt)).scalar_one()
        return RoomRead.model_validate(room)


@fastapi_app.patch("/rooms/{room_id}", response_model=RoomRead, tags=["rooms"])
async def update_room(
    room_update: RoomUpdate,
    room_id: int = Path(..., description="ID of the room to update", gt=0),
    current_user: User = Depends(current_active_user),
):
    """Host endpoint: only room owner can update room data."""
    async with AsyncSessionLocal() as session:
        stmt = select(Room).options(selectinload(Room.owner)).where(Room.id == room_id)
        db_room = (await session.execute(stmt)).scalar_one_or_none()

        if db_room is None:
            raise HTTPException(status_code=404, detail="Room not found")
        if db_room.owner_id != current_user.id:
            raise HTTPException(status_code=403, detail="You can only update your own rooms")

        updates = room_update.model_dump(exclude_unset=True)
        for field, value in updates.items():
            setattr(db_room, field, value)

        await session.commit()
        await session.refresh(db_room)
        return RoomRead.model_validate(db_room)


@fastapi_app.delete("/rooms/{room_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["rooms"])
async def delete_room(
    room_id: int = Path(..., description="ID of the room to delete", gt=0),
    current_user: User = Depends(current_active_user),
):
    """Host endpoint: only room owner can delete room."""
    async with AsyncSessionLocal() as session:
        db_room = (await session.execute(select(Room).where(Room.id == room_id))).scalar_one_or_none()

        if db_room is None:
            raise HTTPException(status_code=404, detail="Room not found")
        if db_room.owner_id != current_user.id:
            raise HTTPException(status_code=403, detail="You can only delete your own rooms")

        await session.delete(db_room)
        await session.commit()
        return None


@fastapi_app.post("/bookings", response_model=BookingRead, tags=["bookings"])
async def create_booking(
    booking_in: BookingCreate,
    current_user: User = Depends(current_active_user),
):
    """Guest endpoint: book someone else's available room."""
    if booking_in.check_out <= booking_in.check_in:
        raise HTTPException(status_code=400, detail="check_out must be after check_in")

    async with AsyncSessionLocal() as session:
        room = (
            await session.execute(select(Room).where(Room.id == booking_in.room_id))
        ).scalar_one_or_none()

        if room is None:
            raise HTTPException(status_code=404, detail="Room not found")
        if room.owner_id == current_user.id:
            raise HTTPException(status_code=400, detail="You cannot book your own room")
        if not room.is_available:
            raise HTTPException(status_code=400, detail="Room is not available")

        overlap_stmt = select(Booking).where(
            Booking.room_id == booking_in.room_id,
            Booking.check_in < booking_in.check_out,
            Booking.check_out > booking_in.check_in,
        )
        overlapping = (await session.execute(overlap_stmt)).scalar_one_or_none()
        if overlapping is not None:
            raise HTTPException(status_code=400, detail="Room is already booked for these dates")

        booking = Booking(
            room_id=booking_in.room_id,
            guest_id=current_user.id,
            check_in=booking_in.check_in,
            check_out=booking_in.check_out,
        )
        session.add(booking)

        # Simplified inventory lock once booking is created.
        room.is_available = False

        await session.commit()
        await session.refresh(booking)
        return BookingRead.model_validate(booking)
