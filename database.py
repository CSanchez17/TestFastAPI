from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy import func, inspect, text

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
    from sqlalchemy.orm import selectinload

    from models import City, Country, Location, Room, User

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

        room_columns = await conn.run_sync(
            lambda sync_conn: {
                col["name"] for col in inspect(sync_conn).get_columns("rooms")
            }
            if inspect(sync_conn).has_table("rooms")
            else set()
        )
        if "location_id" not in room_columns:
            await conn.execute(
                text("ALTER TABLE rooms ADD COLUMN location_id INTEGER")
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
        room_column_rows = (await session.execute(text("PRAGMA table_info(rooms)"))).mappings().all()
        room_columns = {row["name"] for row in room_column_rows}

        async def ensure_seed_user(
            username: str,
            email: str,
            plain_password: str,
            *,
            is_host: bool,
            is_superuser: bool,
        ) -> User:
            user = (
                await session.execute(select(User).where(User.username == username))
            ).scalar_one_or_none()

            if user is None:
                user = User(
                    username=username,
                    is_host=is_host,
                    email=email,
                    hashed_password=password_hash.hash(plain_password),
                    is_active=True,
                    is_superuser=is_superuser,
                    is_verified=True,
                )
                session.add(user)
                await session.flush()
                return user

            user.email = email
            user.is_host = is_host
            user.is_active = True
            user.is_superuser = is_superuser
            user.is_verified = True
            # Keep seed credentials stable for local/dev environments.
            user.hashed_password = password_hash.hash(plain_password)
            await session.flush()
            return user

        admin = await ensure_seed_user(
            "admin",
            "admin@example.com",
            "admin123",
            is_host=True,
            is_superuser=True,
        )
        await ensure_seed_user(
            "master",
            "master@example.com",
            "master",
            is_host=True,
            is_superuser=True,
        )

        # Backfill Location rows for legacy room.location string values.
        if "location" in room_columns:
            legacy_rooms = (
                await session.execute(
                    text("SELECT id, location, location_id FROM rooms")
                )
            ).mappings().all()
            for row in legacy_rooms:
                if row["location_id"]:
                    continue

                location_text = row["location"] or "Unknown location"
                location = Location(
                    address_line=location_text,
                    city="Unknown",
                    country="Unknown",
                    postal_code="00000",
                )
                session.add(location)
                await session.flush()
                await session.execute(
                    text("UPDATE rooms SET location_id = :location_id WHERE id = :room_id"),
                    {"location_id": location.id, "room_id": row["id"]},
                )

        def seed_location(address_line: str, city: str, country: str, postal_code: str) -> Location:
            return Location(
                address_line=address_line,
                city=city,
                country=country,
                postal_code=postal_code,
            )

        async def get_or_create_country(name: str) -> Country:
            country = (
                await session.execute(select(Country).where(Country.name == name))
            ).scalar_one_or_none()
            if country is None:
                country = Country(name=name)
                session.add(country)
                await session.flush()
            return country

        async def get_or_create_city(country_name: str, city_name: str) -> City:
            country = await get_or_create_country(country_name)
            city = (
                await session.execute(
                    select(City).where(City.country_id == country.id, City.name == city_name)
                )
            ).scalar_one_or_none()
            if city is None:
                city = City(name=city_name, country_id=country.id)
                session.add(city)
                await session.flush()
            return city

        existing_country_count = (
            await session.execute(select(Country.id))
        ).scalars().first()
        if existing_country_count is None:
            # Create initial countries and cities if database is empty
            initial_countries_cities = {
                "Portugal": ["Lisbon", "Porto", "Coimbra"],
                "Spain": ["Madrid", "Barcelona", "Valencia"],
                "Germany": ["Berlin", "Munich", "Hamburg"],
                "Italy": ["Rome", "Milan", "Naples"],
            }
            for country_name, cities in initial_countries_cities.items():
                for city_name in cities:
                    await get_or_create_city(country_name, city_name)

        # Keep the catalog aligned with already stored locations.
        existing_locations = (await session.execute(select(Location))).scalars().all()
        for location in existing_locations:
            await get_or_create_city(location.country, location.city)

        # For rooms with invalid locations, assign them to existing cities
        available_rooms = (
            await session.execute(
                select(Room).options(selectinload(Room.location)).where(Room.is_available.is_(True))
            )
        ).scalars().all()

        # Get all existing valid country-city pairs from database
        existing_cities = await session.execute(
            select(City.name, Country.name)
            .join(Country, City.country_id == Country.id)
        )
        valid_pairs = [(country, city) for city, country in existing_cities.all()]

        if valid_pairs:  # Only process if we have valid pairs
            for index, room in enumerate(available_rooms):
                current_location = room.location
                needs_fix = current_location is None
                if not needs_fix:
                    continue

                country, city = valid_pairs[index % len(valid_pairs)]
                await get_or_create_city(country, city)

                location = seed_location(
                    address_line=f"Updated Address {room.id}",
                    city=city,
                    country=country,
                    postal_code=f"10{room.id:03d}",
                )
                session.add(location)
                await session.flush()
                room.location_id = location.id

        stmt = select(Room).where(Room.id.in_([1, 2]))
        existing_rooms = (await session.execute(stmt)).scalars().all()
        existing_ids = {room.id for room in existing_rooms}

        if 1 not in existing_ids:
            location = seed_location("Ocean Avenue 12", "Lisbon", "Portugal", "1100-145")
            await get_or_create_city(location.country, location.city)
            session.add(location)
            await session.flush()
            session.add(
                Room(
                    id=1,
                    title="Suite with Sea View",
                    location_id=location.id,
                    description="Bright suite with balcony and ocean view.",
                    price_per_night=180,
                    is_available=True,
                    owner_id=admin.id,
                )
            )
        if 2 not in existing_ids:
            location = seed_location("Market Street 8", "Berlin", "Germany", "10115")
            await get_or_create_city(location.country, location.city)
            session.add(location)
            await session.flush()
            session.add(
                Room(
                    id=2,
                    title="City Studio",
                    location_id=location.id,
                    description="Compact studio in the city center.",
                    price_per_night=95,
                    is_available=True,
                    owner_id=admin.id,
                )
            )

        # Populate rooms for existing cities if needed
        # Get existing cities from database
        existing_cities_query = await session.execute(
            select(City.name, Country.name)
            .join(Country, City.country_id == Country.id)
        )
        existing_cities = existing_cities_query.all()

        room_templates = [
            {
                "title": "Cozy Apartment in {city}",
                "description": "A comfortable {size} apartment in the heart of {city}. Perfect for tourists and business travelers. Features modern amenities, WiFi, and a fully equipped kitchen.",
                "price_per_night": 85.0,
                "size": "1-bedroom"
            },
            {
                "title": "Luxury Suite with City View",
                "description": "Elegant {size} suite offering stunning views of {city}. Includes premium furnishings, balcony, and concierge service. Ideal for special occasions.",
                "price_per_night": 150.0,
                "size": "2-bedroom"
            },
            {
                "title": "Budget-Friendly Studio",
                "description": "Affordable studio apartment in {city}. Compact but comfortable, with all essential amenities. Great value for budget-conscious travelers.",
                "price_per_night": 55.0,
                "size": "studio"
            },
            {
                "title": "Family-Friendly Townhouse",
                "description": "Spacious {size} townhouse perfect for families. Located in a quiet neighborhood of {city}, with garden access and parking. Fully furnished and child-friendly.",
                "price_per_night": 120.0,
                "size": "3-bedroom"
            },
            {
                "title": "Modern Loft Downtown",
                "description": "Trendy loft apartment in downtown {city}. Industrial-chic design with high ceilings, exposed brick, and contemporary furnishings. Walking distance to attractions.",
                "price_per_night": 95.0,
                "size": "open-plan"
            },
        ]

        # Check if we need to create more rooms (aim for at least 5 rooms per city)
        total_existing_rooms = await session.execute(select(func.count(Room.id)))
        total_rooms = total_existing_rooms.scalar()

        target_rooms_per_city = 5
        target_total_rooms = len(existing_cities) * target_rooms_per_city

        if total_rooms < target_total_rooms:
            for city_name, country_name in existing_cities:
                # Count existing rooms for this city
                city_rooms_count = await session.execute(
                    select(func.count(Room.id))
                    .join(Room.location)
                    .where(Location.city == city_name, Location.country == country_name)
                )
                existing_count = city_rooms_count.scalar()

                # Create missing rooms for this city
                rooms_to_create = target_rooms_per_city - existing_count
                if rooms_to_create > 0:
                    # Get or create location for this city
                    location_query = await session.execute(
                        select(Location).where(Location.city == city_name, Location.country == country_name)
                    )
                    location = location_query.scalar_one_or_none()

                    if location is None:
                        location = Location(
                            address_line=f"Centro Histórico, {city_name}",
                            city=city_name,
                            country=country_name,
                            postal_code=f"{1000 + hash(city_name) % 9000:04d}"
                        )
                        session.add(location)
                        await session.flush()

                    # Create the missing rooms
                    for i in range(rooms_to_create):
                        template = room_templates[i % len(room_templates)]
                        room = Room(
                            title=template["title"].format(city=city_name),
                            location_id=location.id,
                            description=template["description"].format(city=city_name, size=template["size"]),
                            price_per_night=template["price_per_night"],
                            is_available=True,
                            owner_id=admin.id
                        )
                        session.add(room)

            await session.commit()
            print("Sample rooms created successfully.")
