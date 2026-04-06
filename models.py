from sqlalchemy import Column, Integer, String, ForeignKey
from fastapi_users.db import SQLAlchemyBaseUserTable
from sqlalchemy.orm import Mapped, mapped_column, relationship
from database import Base
from typing import List

# Modelo ORM para la tabla students
# Representa el dominio de estudiante dentro de la DB
class Student(Base):
    __tablename__ = "students"

    # El ID se genera automáticamente en la DB
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str]
    age: Mapped[int]
    year: Mapped[str]

    # Campo para saber quién lo creó
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"),
                                               default=1,
                                               server_default="1")  # Asumimos que el admin tiene ID=1
    
    # Relación: Muchos estudiantes pertenecen a un creador
    creator: Mapped["User"] = relationship(back_populates="students")

class User(Base, SQLAlchemyBaseUserTable[int]):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(unique=True, index=True)
    email: Mapped[str] = mapped_column(unique=True, index=True)
    hashed_password: Mapped[str]

    # Relación: Un usuario puede tener muchos estudiantes
    students: Mapped[List["Student"]] = relationship(back_populates="creator")