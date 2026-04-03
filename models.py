from sqlalchemy import Column, Integer, String
from database import Base

# Modelo ORM para la tabla students
# Representa el dominio de estudiante dentro de la DB
class Student(Base):
    __tablename__ = "students"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    age = Column(Integer, nullable=False)
    year = Column(String, nullable=False)
