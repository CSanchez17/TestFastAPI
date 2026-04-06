from markupsafe import Markup, escape
from sqladmin import Admin, ModelView
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload
from wtforms import PasswordField, SelectField
from pwdlib import PasswordHash

from database import engine
from models import Booking, City, Country, Location, Room, User


def detail_link(resource: str, obj) -> str:
    return f"/admin/{resource}/details/{obj.id}"


def render_single_link(resource: str, obj) -> Markup:
    if obj is None:
        return Markup("<span class='text-secondary'>None</span>")
    return Markup(
        f"<a href='{escape(detail_link(resource, obj))}'>{escape(str(obj))}</a>"
    )


def render_link_list(resource: str, objects) -> Markup:
    if not objects:
        return Markup("<span class='text-secondary'>None</span>")
    links = [
        f"<a href='{escape(detail_link(resource, obj))}'>{escape(str(obj))}</a>"
        for obj in objects
    ]
    return Markup("<br>".join(links))


class UserAdmin(ModelView, model=User):
    name = "User"
    name_plural = "Users"
    icon = "fa-solid fa-user"
    column_list = [
        User.id,
        User.username,
        User.email,
        User.is_host,
        User.is_active,
        User.is_superuser,
        User.is_verified,
        "rooms_count",
        "bookings_count",
    ]
    column_details_list = [
        User.id,
        User.username,
        User.email,
        User.is_host,
        User.is_active,
        User.is_superuser,
        User.is_verified,
        "rooms_count",
        "bookings_count",
        "admin_rooms",
        "admin_bookings",
    ]
    column_searchable_list = [User.username, User.email]
    column_sortable_list = [User.id, User.username, User.email]
    form_columns = [
        User.username,
        User.email,
        User.hashed_password,
        User.is_host,
        User.is_active,
        User.is_superuser,
        User.is_verified,
    ]
    form_overrides = {
        "hashed_password": PasswordField,
    }
    form_args = {
        "hashed_password": {
            "label": "Password",
        }
    }
    form_widget_args = {
        "hashed_password": {
            "placeholder": "Enter a new password",
        }
    }
    column_labels = {
        "rooms_count": "Rooms (count)",
        "bookings_count": "Bookings (count)",
        "admin_rooms": "Room References",
        "admin_bookings": "Booking References",
    }
    column_formatters_detail = {
        "admin_rooms": lambda model, _: render_link_list("room", model.admin_rooms),
        "admin_bookings": lambda model, _: render_link_list("booking", model.admin_bookings),
    }

    async def on_model_change(self, data, model, is_created, request):
        username = (data.get("username") or "").strip()
        email = (data.get("email") or "").strip()
        raw_password = (data.get("hashed_password") or "").strip()

        if not username:
            raise ValueError("Username is required")
        if not email:
            raise ValueError("Email is required")

        data["username"] = username
        data["email"] = email

        async with self.session_maker() as session:
            username_owner = (
                await session.execute(select(User).where(User.username == username))
            ).scalar_one_or_none()
            if username_owner is not None and (is_created or username_owner.id != model.id):
                raise ValueError("Username already exists")

            email_owner = (
                await session.execute(
                    select(User).where(func.lower(User.email) == email.lower())
                )
            ).scalar_one_or_none()
            if email_owner is not None and (is_created or email_owner.id != model.id):
                raise ValueError("Email already exists")

        if is_created and not raw_password:
            raise ValueError("Password is required to create a user")

        if not raw_password:
            # Keep the existing password hash if password is empty on edit.
            data.pop("hashed_password", None)
            return

        password_hash = PasswordHash.recommended()
        data["hashed_password"] = password_hash.hash(raw_password)


class LocationAdmin(ModelView, model=Location):
    name = "Location"
    name_plural = "Locations"
    icon = "fa-solid fa-location-dot"
    column_list = [
        Location.id,
        Location.address_line,
        Location.city,
        Location.country,
        Location.postal_code,
        "rooms_count",
    ]
    column_details_list = [
        Location.id,
        Location.address_line,
        Location.city,
        Location.country,
        Location.postal_code,
        "rooms_count",
        Location.rooms,
    ]
    column_searchable_list = [Location.address_line, Location.city, Location.country, Location.postal_code]
    create_template = "sqladmin/location_create.html"
    edit_template = "sqladmin/location_edit.html"
    form_columns = [
        Location.address_line,
        Location.city,
        Location.country,
        Location.postal_code,
    ]
    country_city_map = {}
    form_overrides = {
        "city": SelectField,
        "country": SelectField,
    }
    form_args = {
        "city": {
            "choices": []
        },
        "country": {
            "choices": []
        },
    }
    column_labels = {
        "rooms_count": "Rooms Count",
        Location.rooms: "Room References",
    }
    column_formatters_detail = {
        Location.rooms: lambda model, _: render_link_list("room", model.rooms),
    }

    async def _load_country_city_map(self) -> dict[str, list[str]]:
        async with self.session_maker() as session:
            stmt = (
                select(Country)
                .options(selectinload(Country.cities))
                .order_by(Country.name)
            )
            countries = (await session.execute(stmt)).scalars().all()

        country_city_map = {}
        for country in countries:
            country_city_map[country.name] = sorted(city.name for city in country.cities)
        return country_city_map

    async def scaffold_form(self, rules=None):
        self.country_city_map = await self._load_country_city_map()
        countries = list(self.country_city_map.keys())
        cities = sorted(
            {city for country_cities in self.country_city_map.values() for city in country_cities}
        )
        self.form_args = {
            "city": {
                "choices": [(city, city) for city in cities]
            },
            "country": {
                "choices": [(country, country) for country in countries]
            },
        }
        return await super().scaffold_form(rules)

    async def on_model_change(self, data, model, is_created, request):
        country = data.get("country")
        city = data.get("city")

        self.country_city_map = await self._load_country_city_map()

        if country not in self.country_city_map:
            raise ValueError("Selected country is not supported")

        valid_cities = self.country_city_map[country]
        if city not in valid_cities:
            raise ValueError("Selected city does not belong to the selected country")


class CountryAdmin(ModelView, model=Country):
    name = "Country"
    name_plural = "Countries"
    icon = "fa-solid fa-earth-europe"
    column_list = [Country.id, Country.name]
    column_details_list = [Country.id, Country.name, Country.cities]
    column_searchable_list = [Country.name]
    column_sortable_list = [Country.id, Country.name]
    form_columns = [Country.name]
    column_labels = {
        Country.cities: "Cities",
    }
    column_formatters_detail = {
        Country.cities: lambda model, _: render_link_list("city", model.cities),
    }


class CityAdmin(ModelView, model=City):
    name = "City"
    name_plural = "Cities"
    icon = "fa-solid fa-city"
    column_list = [City.id, City.name, "country_name"]
    column_details_list = [City.id, City.name, City.country]
    column_searchable_list = [City.name]
    column_sortable_list = [City.id, City.name]
    form_columns = [City.name, City.country]
    column_labels = {
        "country_name": "Country",
        City.country: "Country Reference",
    }
    column_formatters_detail = {
        City.country: lambda model, _: render_single_link("country", model.country),
    }


class RoomAdmin(ModelView, model=Room):
    name = "Room"
    name_plural = "Rooms"
    icon = "fa-solid fa-hotel"
    column_list = [
        Room.id,
        Room.title,
        "full_location",
        Room.price_per_night,
        Room.is_available,
        "owner_username",
        "bookings_count",
    ]
    column_details_list = [
        Room.id,
        Room.title,
        "admin_location",
        Room.description,
        Room.price_per_night,
        Room.is_available,
        "admin_owner",
        "owner_username",
        "bookings_count",
        "admin_bookings",
    ]
    column_searchable_list = [Room.title, Room.description]
    column_sortable_list = [Room.id, Room.price_per_night]
    # Keep relationship fields in form so admins can choose from existing lists.
    form_columns = [
        Room.title,
        Room.location,
        Room.description,
        Room.price_per_night,
        Room.is_available,
        Room.owner,
    ]
    column_labels = {
        "full_location": "Location",
        "admin_location": "Location Reference",
        "admin_owner": "Owner Reference",
        "owner_username": "Owner",
        "bookings_count": "Bookings Count",
        "admin_bookings": "Booking References",
    }
    column_formatters_detail = {
        "admin_location": lambda model, _: render_single_link("location", model.admin_location),
        "admin_owner": lambda model, _: render_single_link("user", model.admin_owner),
        "admin_bookings": lambda model, _: render_link_list("booking", model.admin_bookings),
    }


class BookingAdmin(ModelView, model=Booking):
    name = "Booking"
    name_plural = "Bookings"
    icon = "fa-solid fa-calendar-check"
    column_list = [
        Booking.id,
        "room_title",
        "guest_username",
        Booking.start_date,
        Booking.end_date,
        Booking.status,
        Booking.booked_price_per_night,
        "total_price",
    ]
    column_details_list = [
        Booking.id,
        "admin_room",
        "admin_guest",
        "room_title",
        "guest_username",
        Booking.start_date,
        Booking.end_date,
        Booking.status,
        Booking.booked_price_per_night,
        "total_price",
    ]
    column_sortable_list = [Booking.id, Booking.start_date, Booking.end_date, Booking.status]
    form_excluded_columns = [Booking.check_in, Booking.check_out, Booking.room, Booking.guest]
    column_labels = {
        "admin_room": "Room Reference",
        "admin_guest": "Guest Reference",
        "room_title": "Room",
        "guest_username": "Guest",
        "total_price": "Total Price",
        "booked_price_per_night": "Booked Price/Night",
    }
    column_formatters_detail = {
        "admin_room": lambda model, _: render_single_link("room", model.admin_room),
        "admin_guest": lambda model, _: render_single_link("user", model.admin_guest),
    }


def setup_admin(app):
    admin = Admin(app, engine, title="Mini-Booking Admin")
    admin.add_view(UserAdmin)
    admin.add_view(CountryAdmin)
    admin.add_view(CityAdmin)
    admin.add_view(LocationAdmin)
    admin.add_view(RoomAdmin)
    admin.add_view(BookingAdmin)
