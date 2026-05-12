import json
from dataclasses import dataclass
from typing import Any, Dict, Optional

import httpx
import yaml

from app.config import settings


@dataclass
class FetchResult:
    spec: Dict[str, Any]
    etag: Optional[str]
    not_modified: bool = False


class SpecFetcher:
    def __init__(self, timeout: Optional[float] = None):
        self._timeout = timeout if timeout is not None else settings.OPENAPI_SPEC_FETCH_TIMEOUT_SECONDS

    async def fetch(self, url: str, etag: Optional[str] = None) -> FetchResult:
        headers: Dict[str, str] = {"Accept": "application/json, application/yaml, text/yaml"}
        if etag:
            headers["If-None-Match"] = etag

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(url, headers=headers)

        if resp.status_code == 304:
            return FetchResult(spec={}, etag=etag, not_modified=True)

        resp.raise_for_status()

        content_type = (resp.headers.get("content-type") or "").lower()
        body = resp.text
        spec = _parse_body(body, content_type)
        return FetchResult(
            spec=spec,
            etag=resp.headers.get("etag"),
            not_modified=False,
        )


def _parse_body(body: str, content_type: str) -> Dict[str, Any]:
    if "yaml" in content_type:
        loaded = yaml.safe_load(body)
    elif "json" in content_type:
        loaded = json.loads(body)
    else:
        # Unknown content-type — try JSON first, fall back to YAML
        try:
            loaded = json.loads(body)
        except json.JSONDecodeError:
            loaded = yaml.safe_load(body)
    if not isinstance(loaded, dict):
        raise ValueError("spec must deserialize to an object")
    return loaded
