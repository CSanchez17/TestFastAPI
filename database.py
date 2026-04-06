from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker

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

    async with AsyncSessionLocal() as session:
        admin = (
            await session.execute(select(User).where(User.username == "admin"))
        ).scalar_one_or_none()

        if not admin:
            admin = User(
                username="admin",
                email="admin@example.com",
                hashed_password=password_hash.hash("admin123"),
                is_active=True,
                is_superuser=True,
                is_verified=True,
            )
            session.add(admin)
            await session.flush()

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
