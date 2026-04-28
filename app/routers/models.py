from fastapi import APIRouter, Depends
from typing import List, Dict, Any
from app.llm.registry import list_providers
from app.auth import get_current_user, UserClaims

router = APIRouter()


@router.get(
    "/models",
    summary="List available models",
    tags=["Models"],
    response_model=List[Dict[str, Any]],
)
async def list_models(user: UserClaims = Depends(get_current_user)):
    result = []
    for provider_name, provider in list_providers().items():
        for model in await provider.list_models():
            result.append({
                "provider": provider_name,
                "id": model["id"],
                "name": model["name"],
            })
    return result
