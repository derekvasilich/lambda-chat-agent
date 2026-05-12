from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import List, Optional

from app.openapi.auth import RequestContext


@dataclass
class DiscoveryContext:
    request_context: RequestContext
    enabled_specs: List[str] = field(default_factory=list)


_current: ContextVar[Optional[DiscoveryContext]] = ContextVar(
    "openapi_discovery_context", default=None
)


def set_discovery_context(ctx: DiscoveryContext) -> None:
    _current.set(ctx)


def get_discovery_context() -> DiscoveryContext:
    ctx = _current.get()
    if ctx is None:
        raise RuntimeError(
            "DiscoveryContext is not set. The openapi_discovery tool requires per-request "
            "context (enabled_specs, request_context) to be set before invocation."
        )
    return ctx


def clear_discovery_context() -> None:
    _current.set(None)
