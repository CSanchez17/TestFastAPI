#!/usr/bin/env python3
"""
Script to populate the database with sample rooms in Portugal, Spain, Germany, and Italy.
Each country has 3 cities, each city has 5 rooms with complete information.
"""

import asyncio
from sqlalchemy import select
from database import AsyncSessionLocal, init_db
from models import Location, Room, User


async def populate_rooms():
    await init_db()

    async with AsyncSessionLocal() as session:
        # Get the admin user as owner
        admin = (
            await session.execute(select(User).where(User.username == "admin"))
        ).scalar_one_or_none()

        if not admin:
            print("Admin user not found. Please run the app first to create seed users.")
            return

        # Define the data
        countries_cities = {
            "Portugal": ["Lisbon", "Porto", "Coimbra"],
            "Spain": ["Madrid", "Barcelona", "Valencia"],
            "Germany": ["Berlin", "Munich", "Hamburg"],
            "Italy": ["Rome", "Milan", "Naples"],
        }

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

        room_count = 0

        for country, cities in countries_cities.items():
            for city in cities:
                # Create location for this city
                location = Location(
                    address_line=f"Centro Histórico, {city}",
                    city=city,
                    country=country,
                    postal_code=f"{1000 + hash(city) % 9000:04d}"
                )
                session.add(location)
                await session.flush()

                # Create 5 rooms for this location
                for i, template in enumerate(room_templates):
                    room = Room(
                        title=template["title"].format(city=city),
                        location_id=location.id,
                        description=template["description"].format(city=city, size=template["size"]),
                        price_per_night=template["price_per_night"],
                        is_available=True,
                        owner_id=admin.id
                    )
                    session.add(room)
                    room_count += 1

        await session.commit()
        print(f"Successfully created {room_count} rooms across {len(countries_cities)} countries and {sum(len(cities) for cities in countries_cities.values())} cities.")


if __name__ == "__main__":
    asyncio.run(populate_rooms())