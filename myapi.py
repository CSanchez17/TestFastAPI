from fastapi import FastAPI, HTTPException, Path
from sqlalchemy import select
from contextlib import asynccontextmanager

from database import AsyncSessionLocal, init_db
from models import Student
from schemas import StudentRead

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
app = FastAPI(lifespan=lifespan)

# --------------------------------------------------
# Endpoints
# --------------------------------------------------
@app.get("/students/{student_id}", response_model=StudentRead)
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
        return StudentRead(
            student_id=student.id,
            name=student.name,
            age=student.age,
            year=student.year,
        )
