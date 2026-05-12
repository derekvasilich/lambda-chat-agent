import json

import httpx
import pytest
import respx

from app.openapi.fetcher import SpecFetcher


@pytest.mark.asyncio
async def test_fetch_json_spec():
    spec_body = {"openapi": "3.0.0", "paths": {}}
    with respx.mock:
        respx.get("https://example.com/openapi.json").mock(
            return_value=httpx.Response(
                200,
                content=json.dumps(spec_body),
                headers={"content-type": "application/json", "etag": "abc"},
            )
        )

        result = await SpecFetcher().fetch("https://example.com/openapi.json")

    assert result.spec == spec_body
    assert result.etag == "abc"
    assert result.not_modified is False


@pytest.mark.asyncio
async def test_fetch_yaml_spec():
    body = "openapi: 3.0.0\npaths: {}\n"
    with respx.mock:
        respx.get("https://example.com/openapi.yaml").mock(
            return_value=httpx.Response(
                200,
                content=body,
                headers={"content-type": "application/yaml"},
            )
        )

        result = await SpecFetcher().fetch("https://example.com/openapi.yaml")

    assert result.spec["openapi"] == "3.0.0"
    assert result.spec["paths"] == {}


@pytest.mark.asyncio
async def test_fetch_304_not_modified():
    with respx.mock:
        respx.get("https://example.com/openapi.json").mock(
            return_value=httpx.Response(304),
        )

        result = await SpecFetcher().fetch(
            "https://example.com/openapi.json", etag="cached-etag"
        )

    assert result.not_modified is True
    assert result.etag == "cached-etag"


@pytest.mark.asyncio
async def test_fetch_raises_on_5xx():
    with respx.mock:
        respx.get("https://example.com/openapi.json").mock(
            return_value=httpx.Response(500),
        )

        with pytest.raises(httpx.HTTPStatusError):
            await SpecFetcher().fetch("https://example.com/openapi.json")


@pytest.mark.asyncio
async def test_fetch_falls_back_to_yaml_for_unknown_content_type():
    body = "openapi: 3.0.0\npaths: {}\n"
    with respx.mock:
        respx.get("https://example.com/spec").mock(
            return_value=httpx.Response(
                200,
                content=body,
                headers={"content-type": "text/plain"},
            )
        )

        result = await SpecFetcher().fetch("https://example.com/spec")

    assert result.spec["openapi"] == "3.0.0"


@pytest.mark.asyncio
async def test_fetch_non_object_raises():
    with respx.mock:
        respx.get("https://example.com/openapi.json").mock(
            return_value=httpx.Response(
                200,
                content="[1, 2, 3]",
                headers={"content-type": "application/json"},
            )
        )

        with pytest.raises(ValueError):
            await SpecFetcher().fetch("https://example.com/openapi.json")
