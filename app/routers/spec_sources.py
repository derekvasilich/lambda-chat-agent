from fastapi import APIRouter, Depends, HTTPException

from app.auth import get_current_user, UserClaims
from app.dynamodb import get_spec_sources_table
from app.repositories.spec_sources import SpecSourceRepository
from app.schemas.spec_source import (
    SpecSourceCreate,
    SpecSourceListResponse,
    SpecSourceResponse,
)

router = APIRouter()


async def get_spec_repo(
    table=Depends(get_spec_sources_table),
) -> SpecSourceRepository:
    return SpecSourceRepository(table)


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
    repo: SpecSourceRepository = Depends(get_spec_repo),
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
    repo: SpecSourceRepository = Depends(get_spec_repo),
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
    repo: SpecSourceRepository = Depends(get_spec_repo),
    _user: UserClaims = Depends(get_current_user),
):
    try:
        return await repo.create(body)
    except ValueError as e:
        raise HTTPException(
            status_code=409,
            detail={"error": {"code": "conflict", "message": str(e), "details": {}}},
        )


@router.delete(
    "/spec-sources/{spec_id}",
    status_code=204,
    summary="Delete a spec source",
    tags=["SpecSources"],
)
async def delete_spec_source(
    spec_id: str,
    repo: SpecSourceRepository = Depends(get_spec_repo),
    _user: UserClaims = Depends(get_current_user),
):
    deleted = await repo.delete(spec_id)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "not_found", "message": "Spec source not found", "details": {}}},
        )
