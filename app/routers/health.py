import time
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.database import get_db
from app.schemas.health import HealthResponse
from app.llm.registry import list_providers
from app.config import settings

router = APIRouter()
_start_time = time.time()

@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
    description="Returns server status, DB connectivity, LLM reachability, app version, and uptime.",
    tags=["Health"],
)
async def health(db: AsyncSession = Depends(get_db)):
    # DB check
    try:
        await db.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception as e:
        db_status = f"error: {e}"

    # LLM checks
    providers = list_providers()
    llm_status = {}
    for name, provider in providers.items():
        llm_status[name] = await provider.health_check()

    return HealthResponse(
        status="ok" if db_status == "ok" else "degraded",
        version=settings.APP_VERSION,
        uptime_seconds=round(time.time() - _start_time, 2),
        database=db_status,
        llm_providers=llm_status,
    )
