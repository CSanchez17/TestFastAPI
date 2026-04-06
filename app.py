from contextlib import asynccontextmanager
from pathlib import Path as FileSystemPath

from fastapi import Depends, FastAPI, HTTPException, Path, status
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from database import AsyncSessionLocal, init_db
from models import Booking, Location, Room, User
from schemas import (
    BookingCreate,
    DashboardBookingRead,
    BookingRead,
    BookingStatusUpdate,
    GuestDashboardRead,
    HostDashboardRead,
    RoomCreate,
    RoomRead,
    RoomUpdate,
    UserCreate,
    UserRead,
    UserUpdate,
)
from users import auth_backend, current_active_user, fastapi_users
from web.routes import router as web_router

try:
    from admin import setup_admin
except ImportError:
    setup_admin = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


fastapi_app = FastAPI(lifespan=lifespan)
BASE_DIR = FileSystemPath(__file__).resolve().parent
fastapi_app.mount(
    "/web-static",
    StaticFiles(directory=str(BASE_DIR / "static")),
    name="web-static",
)
fastapi_app.include_router(web_router)

if setup_admin is not None:
    setup_admin(fastapi_app)

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


@fastapi_app.post("/hosts/me/activate", response_model=UserRead, tags=["users"])
async def activate_host(current_user: User = Depends(current_active_user)):
    """Enable host role for the current user."""
    async with AsyncSessionLocal() as session:
        db_user = (await session.execute(select(User).where(User.id == current_user.id))).scalar_one()
        if not db_user.is_host:
            db_user.is_host = True
            await session.commit()
            await session.refresh(db_user)
        return UserRead.model_validate(db_user)


@fastapi_app.get("/rooms", response_model=list[RoomRead], tags=["rooms"])
async def list_available_rooms():
    """Public endpoint: list rooms that are currently available."""
    async with AsyncSessionLocal() as session:
        stmt = (
            select(Room)
            .options(selectinload(Room.owner), selectinload(Room.location))
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
        stmt = (
            select(Room)
            .options(selectinload(Room.owner), selectinload(Room.location))
            .where(Room.id == room_id)
        )
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
    if not current_user.is_host:
        raise HTTPException(status_code=403, detail="Only hosts can create rooms")

    async with AsyncSessionLocal() as session:
        location = Location(**room_in.location.model_dump())
        session.add(location)
        await session.flush()

        new_room = Room(
            title=room_in.title,
            location_id=location.id,
            description=room_in.description,
            price_per_night=room_in.price_per_night,
            is_available=room_in.is_available,
            owner_id=current_user.id,
        )
        session.add(new_room)
        await session.commit()

        stmt = (
            select(Room)
            .options(selectinload(Room.owner), selectinload(Room.location))
            .where(Room.id == new_room.id)
        )
        room = (await session.execute(stmt)).scalar_one()
        return RoomRead.model_validate(room)


@fastapi_app.patch("/rooms/{room_id}", response_model=RoomRead, tags=["rooms"])
async def update_room(
    room_update: RoomUpdate,
    room_id: int = Path(..., description="ID of the room to update", gt=0),
    current_user: User = Depends(current_active_user),
):
    """Host endpoint: only room owner can update room data."""
    if not current_user.is_host:
        raise HTTPException(status_code=403, detail="Only hosts can update rooms")

    async with AsyncSessionLocal() as session:
        stmt = (
            select(Room)
            .options(selectinload(Room.owner), selectinload(Room.location))
            .where(Room.id == room_id)
        )
        db_room = (await session.execute(stmt)).scalar_one_or_none()

        if db_room is None:
            raise HTTPException(status_code=404, detail="Room not found")
        if db_room.owner_id != current_user.id:
            raise HTTPException(status_code=403, detail="You can only update your own rooms")

        updates = room_update.model_dump(exclude_unset=True)
        location_updates = updates.pop("location", None)
        for field, value in updates.items():
            setattr(db_room, field, value)

        if location_updates:
            if db_room.location is None:
                location = Location(**location_updates)
                session.add(location)
                await session.flush()
                db_room.location_id = location.id
            else:
                for field, value in location_updates.items():
                    setattr(db_room.location, field, value)

        await session.commit()
        await session.refresh(db_room)
        return RoomRead.model_validate(db_room)


@fastapi_app.delete("/rooms/{room_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["rooms"])
async def delete_room(
    room_id: int = Path(..., description="ID of the room to delete", gt=0),
    current_user: User = Depends(current_active_user),
):
    """Host endpoint: only room owner can delete room."""
    if not current_user.is_host:
        raise HTTPException(status_code=403, detail="Only hosts can delete rooms")

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
    if booking_in.end_date <= booking_in.start_date:
        raise HTTPException(status_code=400, detail="end_date must be after start_date")

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
            Booking.status != "cancelled",
            Booking.start_date < booking_in.end_date,
            Booking.end_date > booking_in.start_date,
        )
        overlapping = (await session.execute(overlap_stmt)).scalar_one_or_none()
        if overlapping is not None:
            raise HTTPException(status_code=400, detail="Room is already booked for these dates")

        booking = Booking(
            room_id=booking_in.room_id,
            guest_id=current_user.id,
            check_in=booking_in.start_date,
            check_out=booking_in.end_date,
            start_date=booking_in.start_date,
            end_date=booking_in.end_date,
            status="confirmed",
            booked_price_per_night=room.price_per_night,
        )
        session.add(booking)

        # Simplified inventory lock once booking is created.
        room.is_available = False

        await session.commit()
        await session.refresh(booking)
        return BookingRead.model_validate(booking)


@fastapi_app.get("/hosts/rooms/me", response_model=list[RoomRead], tags=["rooms"])
async def get_my_rooms(current_user: User = Depends(current_active_user)):
    """Host endpoint: list rooms owned by the authenticated user."""
    if not current_user.is_host:
        raise HTTPException(status_code=403, detail="Only hosts can view owned rooms")

    async with AsyncSessionLocal() as session:
        stmt = (
            select(Room)
            .options(selectinload(Room.owner), selectinload(Room.location))
            .where(Room.owner_id == current_user.id)
            .order_by(Room.id)
        )
        rooms = (await session.execute(stmt)).scalars().all()
        return [RoomRead.model_validate(room) for room in rooms]


@fastapi_app.get("/bookings/me", response_model=list[BookingRead], tags=["bookings"])
async def get_my_bookings(current_user: User = Depends(current_active_user)):
    """Guest endpoint: list bookings created by the authenticated user."""
    async with AsyncSessionLocal() as session:
        stmt = select(Booking).where(Booking.guest_id == current_user.id).order_by(Booking.id)
        bookings = (await session.execute(stmt)).scalars().all()
        return [BookingRead.model_validate(booking) for booking in bookings]


@fastapi_app.get("/dashboard/host", response_model=HostDashboardRead, tags=["dashboard"])
async def host_dashboard(current_user: User = Depends(current_active_user)):
    """Host dashboard with inventory KPIs and reservations with guest info."""
    if not current_user.is_host:
        raise HTTPException(status_code=403, detail="Only hosts can view host dashboard")

    async with AsyncSessionLocal() as session:
        room_ids = (
            await session.execute(select(Room.id).where(Room.owner_id == current_user.id))
        ).scalars().all()

        if not room_ids:
            return HostDashboardRead(
                total_rooms=0,
                total_bookings=0,
                active_bookings=0,
                total_revenue_confirmed=0,
                bookings=[],
            )

        stmt = (
            select(Booking)
            .options(selectinload(Booking.room), selectinload(Booking.guest))
            .where(Booking.room_id.in_(room_ids))
            .order_by(Booking.id.desc())
        )
        bookings = (await session.execute(stmt)).scalars().all()

        items = [
            DashboardBookingRead(
                id=b.id,
                room_id=b.room_id,
                room_title=b.room.title,
                guest_id=b.guest_id,
                guest_username=b.guest.username,
                start_date=b.start_date,
                end_date=b.end_date,
                status=b.status,
                booked_price_per_night=b.booked_price_per_night,
            )
            for b in bookings
        ]

        active_bookings = sum(1 for b in bookings if b.status == "confirmed")
        total_revenue = sum(
            b.booked_price_per_night for b in bookings if b.status == "confirmed"
        )

        return HostDashboardRead(
            total_rooms=len(room_ids),
            total_bookings=len(bookings),
            active_bookings=active_bookings,
            total_revenue_confirmed=total_revenue,
            bookings=items,
        )


@fastapi_app.get("/dashboard/guest", response_model=GuestDashboardRead, tags=["dashboard"])
async def guest_dashboard(current_user: User = Depends(current_active_user)):
    """Guest dashboard with own bookings and spending metrics."""
    async with AsyncSessionLocal() as session:
        stmt = (
            select(Booking)
            .options(selectinload(Booking.room), selectinload(Booking.guest))
            .where(Booking.guest_id == current_user.id)
            .order_by(Booking.id.desc())
        )
        bookings = (await session.execute(stmt)).scalars().all()

        items = [
            DashboardBookingRead(
                id=b.id,
                room_id=b.room_id,
                room_title=b.room.title,
                guest_id=b.guest_id,
                guest_username=b.guest.username,
                start_date=b.start_date,
                end_date=b.end_date,
                status=b.status,
                booked_price_per_night=b.booked_price_per_night,
            )
            for b in bookings
        ]

        active_bookings = sum(1 for b in bookings if b.status == "confirmed")
        total_spent = sum(
            b.booked_price_per_night for b in bookings if b.status == "confirmed"
        )

        return GuestDashboardRead(
            total_bookings=len(bookings),
            active_bookings=active_bookings,
            total_spent_confirmed=total_spent,
            bookings=items,
        )


@fastapi_app.patch("/bookings/{booking_id}/status", response_model=BookingRead, tags=["bookings"])
async def update_booking_status(
    payload: BookingStatusUpdate,
    booking_id: int = Path(..., description="ID of the booking", gt=0),
    current_user: User = Depends(current_active_user),
):
    """Guest can cancel own booking; host can confirm/cancel bookings for own rooms."""
    async with AsyncSessionLocal() as session:
        stmt = (
            select(Booking)
            .options(selectinload(Booking.room))
            .where(Booking.id == booking_id)
        )
        booking = (await session.execute(stmt)).scalar_one_or_none()
        if booking is None:
            raise HTTPException(status_code=404, detail="Booking not found")

        is_guest_owner = booking.guest_id == current_user.id
        is_room_host = booking.room.owner_id == current_user.id

        if not (is_guest_owner or is_room_host):
            raise HTTPException(status_code=403, detail="You do not have permission to update this booking")

        if is_guest_owner and payload.status != "cancelled":
            raise HTTPException(status_code=403, detail="Guests can only cancel their own bookings")

        booking.status = payload.status
        if payload.status == "cancelled":
            booking.room.is_available = True

        await session.commit()
        await session.refresh(booking)
        return BookingRead.model_validate(booking)
