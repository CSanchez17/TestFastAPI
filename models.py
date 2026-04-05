from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from database import Base

# Modelo ORM para la tabla students
# Representa el dominio de estudiante dentro de la DB
class Student(Base):
    __tablename__ = "students"

    # El ID se genera automáticamente en la DB
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str]
    age: Mapped[int]
    year: Mapped[str]
