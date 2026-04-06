from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy import inspect, text

# SQLite database for the mini-booking project.
DATABASE_URL = "sqlite+aiosqlite:///booking.db"

engine = create_async_engine(DATABASE_URL, echo=False, future=True)

AsyncSessionLocal = sessionmaker(
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession,
)

Base = declarative_base()


async def init_db():
    from pwdlib import PasswordHash
    from sqlalchemy import select

    from models import Room, User

    password_hash = PasswordHash.recommended()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        # Lightweight compatibility migrations for existing SQLite files.
        user_columns = await conn.run_sync(
            lambda sync_conn: {
                col["name"] for col in inspect(sync_conn).get_columns("users")
            }
            if inspect(sync_conn).has_table("users")
            else set()
        )
        if "is_host" not in user_columns:
            await conn.execute(
                text("ALTER TABLE users ADD COLUMN is_host BOOLEAN NOT NULL DEFAULT 0")
            )

        booking_columns = await conn.run_sync(
            lambda sync_conn: {
                col["name"] for col in inspect(sync_conn).get_columns("bookings")
            }
            if inspect(sync_conn).has_table("bookings")
            else set()
        )

        if "start_date" not in booking_columns and "check_in" in booking_columns:
            await conn.execute(text("ALTER TABLE bookings ADD COLUMN start_date DATE"))
            await conn.execute(text("UPDATE bookings SET start_date = check_in"))
        if "end_date" not in booking_columns and "check_out" in booking_columns:
            await conn.execute(text("ALTER TABLE bookings ADD COLUMN end_date DATE"))
            await conn.execute(text("UPDATE bookings SET end_date = check_out"))
        if "status" not in booking_columns:
            await conn.execute(
                text("ALTER TABLE bookings ADD COLUMN status VARCHAR NOT NULL DEFAULT 'confirmed'")
            )
        if "booked_price_per_night" not in booking_columns:
            await conn.execute(
                text("ALTER TABLE bookings ADD COLUMN booked_price_per_night FLOAT NOT NULL DEFAULT 0")
            )
            await conn.execute(
                text(
                    "UPDATE bookings SET booked_price_per_night = "
                    "(SELECT rooms.price_per_night FROM rooms WHERE rooms.id = bookings.room_id)"
                )
            )

    async with AsyncSessionLocal() as session:
        admin = (
            await session.execute(select(User).where(User.username == "admin"))
        ).scalar_one_or_none()

        if not admin:
            admin = User(
                username="admin",
                is_host=True,
                email="admin@example.com",
                hashed_password=password_hash.hash("admin123"),
                is_active=True,
                is_superuser=True,
                is_verified=True,
            )
            session.add(admin)
            await session.flush()
        elif not admin.is_host:
            admin.is_host = True

        stmt = select(Room).where(Room.id.in_([1, 2]))
        existing_rooms = (await session.execute(stmt)).scalars().all()
        existing_ids = {room.id for room in existing_rooms}

        if 1 not in existing_ids:
            session.add(
                Room(
                    id=1,
                    title="Suite with Sea View",
                    description="Bright suite with balcony and ocean view.",
                    price_per_night=180,
                    is_available=True,
                    owner_id=admin.id,
                )
            )
        if 2 not in existing_ids:
            session.add(
                Room(
                    id=2,
                    title="City Studio",
                    description="Compact studio in the city center.",
                    price_per_night=95,
                    is_available=True,
                    owner_id=admin.id,
                )
            )

        await session.commit()
