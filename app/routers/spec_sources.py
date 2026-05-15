from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.auth import get_current_user, UserClaims
from app.postgres import get_spec_source_repo
from app.repositories.spec_sources_pg import SpecSourceRepositoryPG
from app.schemas.spec_source import (
    SpecSourceCreate,
    SpecSourceListResponse,
    SpecSourceResponse,
)
from app.tools.registry import get_tool

router = APIRouter()


async def get_spec_repo(
    repo=Depends(get_spec_source_repo),
) -> SpecSourceRepositoryPG:
    return repo


# TODO(admin): writes (POST, DELETE, refresh) should be gated on the inbound
# Cognito access token carrying a cognito:groups claim containing "admin".
# v1 ships with any-authenticated-user access; lock down before production.


@router.get(
    "/spec-sources",
    response_model=SpecSourceListResponse,
    summary="List registered OpenAPI spec sources",
    tags=["SpecSources"],
)
async def list_spec_sources(
    repo: SpecSourceRepositoryPG = Depends(get_spec_repo),
    _user: UserClaims = Depends(get_current_user),
):
    items = await repo.list()
    return SpecSourceListResponse(items=items)


@router.get(
    "/spec-sources/{spec_id}",
    response_model=SpecSourceResponse,
    summary="Get a single spec source",
    tags=["SpecSources"],
)
async def get_spec_source(
    spec_id: str,
    repo: SpecSourceRepositoryPG = Depends(get_spec_repo),
    _user: UserClaims = Depends(get_current_user),
):
    spec = await repo.get(spec_id)
    if spec is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "not_found", "message": "Spec source not found", "details": {}}},
        )
    return spec


@router.post(
    "/spec-sources",
    response_model=SpecSourceResponse,
    status_code=201,
    summary="Register a new OpenAPI spec source",
    tags=["SpecSources"],
)
async def create_spec_source(
    body: SpecSourceCreate,
    repo: SpecSourceRepositoryPG = Depends(get_spec_repo),
    _user: UserClaims = Depends(get_current_user),
):
    try:
        return await repo.create(body)
    except ValueError as e:
        raise HTTPException(
            status_code=409,
            detail={"error": {"code": "conflict", "message": str(e), "details": {}}},
        )


@router.post(
    "/spec-sources/{spec_id}/refresh",
    response_model=dict[str, Any],
    summary="Refresh an OpenAPI spec source and re-index its operations",
    tags=["SpecSources"],
)
async def refresh_spec_source(
    spec_id: str,
    repo: SpecSourceRepositoryPG = Depends(get_spec_repo),
    _user: UserClaims = Depends(get_current_user),
):
    spec = await repo.get(spec_id)
    if spec is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "not_found", "message": "Spec source not found", "details": {}}},
        )

    tool = get_tool("openapi_discovery")
    if tool is None or not hasattr(tool, "registry"):
        raise HTTPException(
            status_code=500,
            detail={"error": {"code": "server_error", "message": "OpenAPI discovery tool is unavailable", "details": {}}},
        )

    entry = await tool.registry.force_reload(spec)
    return {
        "spec_id": spec_id,
        "status": "refreshed",
        "operation_count": len(entry.operations),
    }


@router.delete(
    "/spec-sources/{spec_id}",
    status_code=204,
    summary="Delete a spec source",
    tags=["SpecSources"],
)
async def delete_spec_source(
    spec_id: str,
    repo: SpecSourceRepositoryPG = Depends(get_spec_repo),
    _user: UserClaims = Depends(get_current_user),
):
    deleted = await repo.delete(spec_id)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "not_found", "message": "Spec source not found", "details": {}}},
        )
    return None
