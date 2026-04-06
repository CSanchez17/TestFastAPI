from fastapi import Depends
from fastapi_users import FastAPIUsers, BaseUserManager, IntegerIDMixin
from fastapi_users.authentication import BearerTransport, JWTStrategy, AuthenticationBackend
from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from database import AsyncSessionLocal
from models import User

# Configuración de transporte (Bearer tokens)
bearer_transport = BearerTransport(tokenUrl="auth/jwt/login")

# Estrategia JWT
SECRET = "SECRET_KEY_CHANGE_THIS_IN_PRODUCTION"


class UserManager(IntegerIDMixin, BaseUserManager[User, int]):
    reset_password_token_secret = SECRET
    verification_token_secret = SECRET

    async def authenticate(self, credentials: OAuth2PasswordRequestForm) -> User | None:
        """Allow login with either username or email in the username field."""
        statement = select(User).where(
            (User.username == credentials.username)
            | (func.lower(User.email) == func.lower(credentials.username))
        )
        result = await self.user_db.session.execute(statement)
        user = result.scalar_one_or_none()

        if user is None:
            # Mitigate timing attacks when user does not exist.
            self.password_helper.hash(credentials.password)
            return None

        verified, updated_password_hash = self.password_helper.verify_and_update(
            credentials.password, user.hashed_password
        )
        if not verified:
            return None

        if updated_password_hash is not None:
            await self.user_db.update(user, {"hashed_password": updated_password_hash})

        return user

def get_jwt_strategy() -> JWTStrategy:
    return JWTStrategy(secret=SECRET, lifetime_seconds=3600)

# Backend de autenticación
auth_backend = AuthenticationBackend(
    name="jwt",
    transport=bearer_transport,
    get_strategy=get_jwt_strategy,
)

# Función helper para obtener sesión async
async def get_async_session():
    async with AsyncSessionLocal() as session:
        yield session

# Database adapter para usuarios
async def get_user_db(session: AsyncSession = Depends(get_async_session)):
    yield SQLAlchemyUserDatabase(session, User)


async def get_user_manager(user_db=Depends(get_user_db)):
    yield UserManager(user_db)

# Instancia de FastAPI Users
fastapi_users = FastAPIUsers[User, int](get_user_manager, [auth_backend])

# Dependencias para proteger rutas
current_active_user = fastapi_users.current_user(active=True)