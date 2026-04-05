from pydantic import BaseModel, Field, ConfigDict

# 1. Esquema Base: Campos que comparten tanto la creación como la lectura
class StudentBase(BaseModel):
    name: str
    age: int
    year: str

# 2. Esquema para CREAR: Se usa en el POST (Request Body)
# No pedimos student_id porque la DB lo genera solo
class StudentCreate(StudentBase):
    pass 

# 3. Esquema para LEER: Se usa en el GET (Response Body)
# Hereda de StudentBase y agrega el ID que ya existe en la DB
class StudentRead(StudentBase):
    # Usamos alias para mapear 'id' (DB) a 'student_id' (API)
    student_id: int = Field(alias="id")

    model_config = ConfigDict(
        from_attributes=True,  # Antes: orm_mode
    )