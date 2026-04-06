from fastapi import FastAPI, HTTPException, Path, status, Depends
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from contextlib import asynccontextmanager
from sqlalchemy.orm import selectinload

from database import AsyncSessionLocal, init_db
from models import Student, User
from schemas import StudentRead, StudentCreate, UserRead, UserCreate, UserUpdate
from users import fastapi_users, current_active_user, auth_backend
from auth import verify_password, create_access_token

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
# Routers de FastAPI Users
# --------------------------------------------------
# Endpoints de autenticación y registro
fastapi_app.include_router(
    fastapi_users.get_auth_router(auth_backend),
    prefix="/auth/jwt",
    tags=["auth"]
)

# Endpoints de registro
fastapi_app.include_router(
    fastapi_users.get_register_router(UserRead, UserCreate),
    prefix="/auth",
    tags=["auth"]
)

# Endpoints de usuarios (requiere autenticación)
fastapi_app.include_router(
    fastapi_users.get_users_router(UserRead, UserUpdate),
    prefix="/users",
    tags=["users"]
)


@fastapi_app.get("/all-users", response_model=list[UserRead], tags=["users"])
async def get_all_users(current_user: User = Depends(current_active_user)):
    """Return all registered users (requires an authenticated user)."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).order_by(User.id))
        users = result.scalars().all()
        return [UserRead.model_validate(user) for user in users]

# --------------------------------------------------
# Endpoints
# --------------------------------------------------
@fastapi_app.get("/student/{student_id}", response_model=StudentRead)
async def get_student(student_id: int=Path(..., description="ID of the student to retrieve",gt=0)):
    """Get one student by ID."""
    # Cada request usa una nueva sesión de DB (async)
    async with AsyncSessionLocal() as session:
        # Construye la consulta ORM para buscar el estudiante
        stmt = select(Student).options(
                selectinload(Student.creator)).where(Student.id == student_id)

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
    """Get the full list of students."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Student).options(selectinload(Student.creator)))
        students = result.scalars().all()
        # FastAPI y Pydantic hacen el mapeo automáticamente por ti:
        return students
    
@fastapi_app.post("/student", response_model=StudentRead)
async def create_student(student_in: StudentCreate,
                         current_user: User = Depends(current_active_user)): # <-- Entra SIN ID
    """Create a student owned by the authenticated user."""
    async with AsyncSessionLocal() as session:
        # 1. Convertimos el esquema de entrada a modelo de SQLAlchemy
        new_student = Student(
            name=student_in.name,
            age=student_in.age,
            year=student_in.year,
            created_by_id=current_user.id # <-- Asignamos el creador actual
        )

        session.add(new_student)
        await session.commit() # <-- Aquí la DB genera el ID

        # 2. RECARGAMOS al estudiante con su relación 'creator'
        # Esto es vital para que al salir del 'async with' los datos ya estén ahí
        stmt = (
            select(Student)
            .options(selectinload(Student.creator))
            .where(Student.id == new_student.id)
        )
        result = await session.execute(stmt)
        student_with_creator = result.scalar_one()

        return student_with_creator # <-- FastAPI lo convierte automáticamente a StudentRead (CON ID)


@fastapi_app.delete("/student/{student_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_student(
    student_id: int = Path(..., description="ID of the student to delete", gt=0),
    current_user: User = Depends(current_active_user),
):
    """Delete a student only if the authenticated user is the owner."""
    async with AsyncSessionLocal() as session:
        print(f"Delete requested by user: {current_user}")
        # 1. Buscar si el estudiante existe
        result = await session.execute(select(Student).where(Student.id == student_id))
        db_student = result.scalar_one_or_none()

        if db_student is None:
            raise HTTPException(status_code=404, detail="Student not found")

        # 3. CONTROL DE ACCESO: ¿Es el dueño?
        if db_student.created_by_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, 
                detail="You do not have permission to delete this student"
            )

        # 4. Borrar y confirmar
        await session.delete(db_student)
        await session.commit()
        
        # Al usar 204 No Content, no devolvemos cuerpo (return None)
        return None
    

# Endpoint para obtener el Token (Login)
@fastapi_app.post("/token")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """Custom token endpoint for username/password login."""
    async with AsyncSessionLocal() as session:
        # get_user_by_username manual:
        result = await session.execute(select(User).where(User.username == form_data.username))
        user = result.scalar_one_or_none()
        
        if not user or not verify_password(form_data.password, user.hashed_password):
            raise HTTPException(status_code=401, detail="Invalid username or password")
        
        access_token = create_access_token(data={"sub": user.username})
        return {"access_token": access_token, "token_type": "bearer"}