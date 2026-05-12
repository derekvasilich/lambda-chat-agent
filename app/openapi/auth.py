import base64
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional, Protocol


@dataclass
class RequestContext:
    user_sub: Optional[str] = None
    bearer_token: Optional[str] = None


class AuthResolver(Protocol):
    async def headers_for(
        self,
        spec_id: str,
        auth_config: Dict[str, Any],
        request_context: RequestContext,
    ) -> Dict[str, str]: ...


class CompositeAuthResolver:
    async def headers_for(
        self,
        spec_id: str,
        auth_config: Dict[str, Any],
        request_context: RequestContext,
    ) -> Dict[str, str]:
        kind = auth_config.get("type")
        if kind == "none":
            return {}
        if kind == "passthrough_jwt":
            return _passthrough_jwt(auth_config, request_context)
        if kind == "bearer_env":
            return _bearer_env(auth_config)
        if kind == "api_key_env":
            return _api_key_env(auth_config)
        if kind == "basic_env":
            return _basic_env(auth_config)
        if kind == "static":
            return _static(auth_config)
        raise ValueError(f"Unknown auth type: {kind!r}")


def _passthrough_jwt(cfg: Dict[str, Any], ctx: RequestContext) -> Dict[str, str]:
    if not ctx.bearer_token:
        raise PermissionError(
            "passthrough_jwt requires an inbound bearer token, but none was present on the request"
        )
    header_name = cfg.get("header_name") or "Authorization"
    return {header_name: f"Bearer {ctx.bearer_token}"}


def _bearer_env(cfg: Dict[str, Any]) -> Dict[str, str]:
    env_var = cfg["env_var"]
    value = os.environ.get(env_var)
    if not value:
        raise PermissionError(f"Environment variable {env_var!r} is not set")
    return {"Authorization": f"Bearer {value}"}


def _api_key_env(cfg: Dict[str, Any]) -> Dict[str, str]:
    env_var = cfg["env_var"]
    header = cfg["header"]
    value = os.environ.get(env_var)
    if not value:
        raise PermissionError(f"Environment variable {env_var!r} is not set")
    return {header: value}


def _basic_env(cfg: Dict[str, Any]) -> Dict[str, str]:
    user = os.environ.get(cfg["username_env"])
    pw = os.environ.get(cfg["password_env"])
    if not user or not pw:
        raise PermissionError(
            f"Environment variables {cfg['username_env']!r} and/or {cfg['password_env']!r} not set"
        )
    encoded = base64.b64encode(f"{user}:{pw}".encode()).decode()
    return {"Authorization": f"Basic {encoded}"}


def _static(cfg: Dict[str, Any]) -> Dict[str, str]:
    headers = cfg.get("headers", {})
    if not isinstance(headers, dict):
        return {}
    return {str(k): str(v) for k, v in headers.items()}
