import time

from fastapi import APIRouter, Depends
import httpx
from app.dynamodb import get_conversations_table
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
async def health(conv_table=Depends(get_conversations_table)):
    try:
        await conv_table.load()
        db_status = "ok"
    except Exception as e:
        db_status = f"error: {e}"

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(settings.OAUTH2_JWKS_URL, timeout=10)
            resp.raise_for_status()
        auth_status = "ok"
    except Exception as e:
        auth_status = f"error: {e}"

    providers = list_providers()
    llm_status = {}
    for name, provider in providers.items():
        llm_status[name] = await provider.health_check()

    return HealthResponse(
        status="ok" if db_status == "ok" else "degraded",
        version=settings.APP_VERSION,
        uptime_seconds=round(time.time() - _start_time, 2),
        database=db_status,
        authentication=auth_status,
        llm_providers=llm_status,
    )
