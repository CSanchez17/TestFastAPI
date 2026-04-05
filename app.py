from fastapi import FastAPI, HTTPException, Path, status
from sqlalchemy import select
from contextlib import asynccontextmanager

from database import AsyncSessionLocal, init_db
from models import Student
from schemas import StudentRead, StudentCreate

# --------------------------------------------------
# FastAPI lifecycle: inicialización de recursos
# --------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Llamamos a init_db cuando la app arranca (antes de aceptar requests)
    await init_db()
    # Después de la inicialización, la app queda disponible
    yield
    # Aquí podríamos limpiar recursos si fuese necesario al shutdown

# Crea la app FastAPI usando el gestor de ciclo de vida `lifespan`
fastapi_app = FastAPI(lifespan=lifespan)

# --------------------------------------------------
# Endpoints
# --------------------------------------------------
@fastapi_app.get("/student/{student_id}", response_model=StudentRead)
async def get_student(student_id: int=Path(..., description="ID of the student to retrieve",gt=0)):
    # Cada request usa una nueva sesión de DB (async)
    async with AsyncSessionLocal() as session:
        # Construye la consulta ORM para buscar el estudiante
        stmt = select(Student).where(Student.id == student_id)

        # Ejecuta la consulta de forma asíncrona
        result = await session.execute(stmt)
        student = result.scalar_one_or_none()  # Obtén 1 resultado o None

        # 404 si no existe el estudiante
        if student is None:
            raise HTTPException(status_code=404, detail="Student not found")

        # Mapea el modelo ORM a Pydantic response schema
        return StudentRead.model_validate(student)

@fastapi_app.get("/students", response_model=list[StudentRead])
async def get_all_students():
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Student))
        students = result.scalars().all()
        # FastAPI y Pydantic hacen el mapeo automáticamente por ti:
        return students
    
@fastapi_app.post("/student", response_model=StudentRead)
async def create_student(student_in: StudentCreate): # <-- Entra SIN ID
    async with AsyncSessionLocal() as session:
        # 1. Convertimos el esquema de entrada a modelo de SQLAlchemy
        db_student = Student(
            name=student_in.name,
            age=student_in.age,
            year=student_in.year
        )
        
        session.add(db_student)
        await session.commit() # <-- Aquí la DB genera el ID
        await session.refresh(db_student) # <-- Traemos el ID generado al objeto
        
        return db_student # <-- FastAPI lo convierte automáticamente a StudentRead (CON ID)
    

@fastapi_app.delete("/student/{student_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_student(student_id: int):
    async with AsyncSessionLocal() as session:
        # 1. Buscar si el estudiante existe
        result = await session.execute(select(Student).where(Student.id == student_id))
        db_student = result.scalar_one_or_none()

        # 2. Si no existe, lanzar un error 404
        if not db_student:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail=f"Student mit ID {student_id} nicht gefunden"
            )

        # 3. Borrar y confirmar
        await session.delete(db_student)
        await session.commit()
        
        # Al usar 204 No Content, no devolvemos cuerpo (return None)
        return None