from datetime import datetime
from typing import Annotated, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field


SPEC_ID_PATTERN = r"^[a-z][a-z0-9_]{0,31}$"


class AuthNone(BaseModel):
    type: Literal["none"]


class AuthPassthroughJWT(BaseModel):
    type: Literal["passthrough_jwt"]
    header_name: Optional[str] = Field(default=None, examples=["Authorization"])


class AuthBearerEnv(BaseModel):
    type: Literal["bearer_env"]
    env_var: str = Field(min_length=1, examples=["BILLING_API_TOKEN"])


class AuthApiKeyEnv(BaseModel):
    type: Literal["api_key_env"]
    env_var: str = Field(min_length=1, examples=["INVENTORY_API_KEY"])
    header: str = Field(min_length=1, examples=["X-API-Key"])


class AuthBasicEnv(BaseModel):
    type: Literal["basic_env"]
    username_env: str = Field(min_length=1)
    password_env: str = Field(min_length=1)


class AuthStatic(BaseModel):
    type: Literal["static"]
    headers: Dict[str, str]


AuthConfig = Annotated[
    Union[
        AuthNone,
        AuthPassthroughJWT,
        AuthBearerEnv,
        AuthApiKeyEnv,
        AuthBasicEnv,
        AuthStatic,
    ],
    Field(discriminator="type"),
]


class SpecSourceCreate(BaseModel):
    id: str = Field(pattern=SPEC_ID_PATTERN, examples=["billing"])
    url: str = Field(min_length=1, examples=["https://billing.internal/openapi.json"])
    description: str = Field(
        min_length=1,
        max_length=500,
        examples=["Invoices, refunds, subscriptions, payment methods."],
    )
    auth: AuthConfig

    model_config = {"json_schema_extra": {"example": {
        "id": "billing",
        "url": "https://billing.internal/openapi.json",
        "description": "Invoices, refunds, subscriptions, payment methods.",
        "auth": {"type": "passthrough_jwt"},
    }}}


class SpecSourceResponse(BaseModel):
    id: str
    url: str
    description: str
    auth: AuthConfig
    cache_etag: Optional[str] = None
    last_fetched_at: Optional[datetime] = None
    operation_count: Optional[int] = None
    created_at: datetime
    updated_at: datetime


class SpecSourceListResponse(BaseModel):
    items: List[SpecSourceResponse]
