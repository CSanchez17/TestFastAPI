from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# URL de la DB, usando driver async para SQLite
DATABASE_URL = "sqlite+aiosqlite:///students.db"

# Crea el engine asíncrono (SQLAlchemy 1.4+)
engine = create_async_engine(DATABASE_URL, echo=False, future=True)

# Factory de sesiones asíncronas
AsyncSessionLocal = sessionmaker(
    bind=engine,
    expire_on_commit=False,  # evita expire de objetos al commit
    class_=AsyncSession,
)

# Base declarativa para modelos ORM
Base = declarative_base()

# Inicializa la base de datos y datos semilla
async def init_db():
    from models import Student, User
    from passlib.context import CryptContext

    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

    # Crea tablas basadas en los modelos (si no existen)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Inserta datos iniciales si no existen
    async with AsyncSessionLocal() as session:
        from sqlalchemy import select

        # 1. Crear un usuario administrador si no existe
        result = await session.execute(select(User).where(User.username == "admin"))
        admin = result.scalar_one_or_none()

        if not admin:
            admin = User(
                id=1,
                username="admin",
                email="admin@example.com",
                hashed_password=pwd_context.hash("admin123"),
                is_active=True,
                is_superuser=True,
                is_verified=True
            )
            session.add(admin)

        # 2. Crear estudiantes de ejemplo si no existen
        stmt = select(Student).where(Student.id.in_([1, 2]))
        existing = (await session.execute(stmt)).scalars().all()
        existing_ids = {s.id for s in existing}

        if 1 not in existing_ids:
            session.add(Student(id=1, name="Alice", age=20, year="year 12", created_by_id=1))
        if 2 not in existing_ids:
            session.add(Student(id=2, name="Bob", age=22, year="year 15", created_by_id=1))

        await session.commit()