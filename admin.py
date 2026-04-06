from sqladmin import Admin, ModelView

from database import engine
from models import Booking, Room, User


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
    ]
    column_searchable_list = [User.username, User.email]
    column_sortable_list = [User.id, User.username, User.email]


class RoomAdmin(ModelView, model=Room):
    name = "Room"
    name_plural = "Rooms"
    icon = "fa-solid fa-hotel"
    column_list = [
        Room.id,
        Room.title,
        Room.price_per_night,
        Room.is_available,
        Room.owner_id,
        Room.owner,
    ]
    column_searchable_list = [Room.title, Room.description]
    column_sortable_list = [Room.id, Room.price_per_night]


class BookingAdmin(ModelView, model=Booking):
    name = "Booking"
    name_plural = "Bookings"
    icon = "fa-solid fa-calendar-check"
    column_list = [
        Booking.id,
        Booking.room,
        Booking.guest,
        Booking.start_date,
        Booking.end_date,
        Booking.status,
        Booking.booked_price_per_night,
    ]
    column_sortable_list = [Booking.id, Booking.start_date, Booking.end_date, Booking.status]


def setup_admin(app):
    admin = Admin(app, engine, title="Mini-Booking Admin")
    admin.add_view(UserAdmin)
    admin.add_view(RoomAdmin)
    admin.add_view(BookingAdmin)
