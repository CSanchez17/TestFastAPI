from pydantic import BaseModel

# Esquema de lectura de estudiante para respuestas de la API
# `orm_mode = True` permite la conversión desde instancias ORM
class StudentRead(BaseModel):
    student_id: int
    name: str
    age: int
    year: str

    class Config:
        orm_mode = True
