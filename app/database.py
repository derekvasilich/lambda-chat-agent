import os
import ssl
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from app.config import settings

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CERT_PATH = os.path.join(BASE_DIR, "global-bundle.pem")

if not os.path.exists(CERT_PATH):
    raise FileNotFoundError(f"SSL certificate not found at {CERT_PATH}")

ssl_ctx = ssl.create_default_context(cafile=CERT_PATH)
ssl_ctx.verify_mode = ssl.CERT_REQUIRED

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    future=True,
    pool_size=0 if "sqlite" in settings.DATABASE_URL else 1,
    max_overflow=0,
    connect_args={
        "check_same_thread": False
    } if "sqlite" in settings.DATABASE_URL else {
        "ssl": ssl_ctx
    },
)

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
