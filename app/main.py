# import asyncio

# # This patches the event loop to prevent the 'Device or resource busy' error
# class SimpleResolver(asyncio.DefaultEventLoopPolicy):
#     def get_event_loop(self):
#         loop = super().get_event_loop()
#         # This is a workaround for Python 3.12 DNS issues in Lambda
#         return loop

# # Apply the patch immediately
# asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())

import structlog
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from app.config import settings
from app.database import engine, Base
from app.middleware.rate_limit import limiter
from app.routers import health, conversations, messages, config, models

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.add_log_level,
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(
        getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    ),
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Log startup for CloudWatch debugging
    print("Lambda Cold Start: Initializing resources...")
    # Skip Base.metadata.create_all here for speed. 
    # Run it once manually or via a migration script.
    # run_migrations()
    yield
    # Clean up on shutdown
    await engine.dispose()

app = FastAPI(
    title="Chat Agent API",
    description="Production-ready AI agent chat API with per-user memory, multi-LLM support, and tool integration.",
    version=settings.APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS
origins = settings.cors_origins_list
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# Structured error handler
@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    if hasattr(exc, "status_code") and hasattr(exc, "detail"):
        detail = exc.detail
        if isinstance(detail, dict):
            return JSONResponse(status_code=exc.status_code, content=detail)
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": "http_error", "message": str(detail), "details": {}}},
        )
    structlog.get_logger().error("unhandled_exception", exc=str(exc))
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "internal_error", "message": "Internal server error", "details": {}}},
    )

# Routers
PREFIX = "/v1"

app.include_router(health.router, prefix=PREFIX)
app.include_router(conversations.router, prefix=PREFIX)
app.include_router(messages.router, prefix=PREFIX)
app.include_router(config.router, prefix=PREFIX)
app.include_router(models.router, prefix=PREFIX)

handler = Mangum(app, lifespan="on");
