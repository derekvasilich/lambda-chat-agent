from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    OAUTH2_JWKS_URL: str = ""
    OAUTH2_AUDIENCE: str = ""
    OAUTH2_ISSUER: str = ""
    OAUTH2_AUTH_URL: str = ""
    OAUTH2_TOKEN_URL: str = ""

    S3_BUCKET: str = ""

    DEFAULT_LLM_PROVIDER: str = "openai"
    DEFAULT_MODEL: str = "gpt-4o"
    ANTHROPIC_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    CUSTOM_LLM_BASE_URL: str = ""
    CUSTOM_LLM_API_KEY: str = "none"
    CUSTOM_LLM_MODEL: str = "llama3"

    RATE_LIMIT_RPM: int = 60
    MAX_HISTORY_MESSAGES: int = 50
    DEFAULT_SYSTEM_PROMPT: str = "You are a helpful AI assistant."

    CORS_ORIGINS: str = "*"
    APP_VERSION: str = "0.1.0"
    LOG_LEVEL: str = "INFO"

    DYNAMODB_TABLE_CONVERSATIONS: str = "chat_conversations"
    DYNAMODB_TABLE_MESSAGES: str = "chat_messages"
    DYNAMODB_TABLE_SPEC_SOURCES: str = "chat_spec_sources"
    DYNAMODB_ENDPOINT_URL: str = ""  # empty = real AWS; "http://localhost:8000" for DynamoDB Local
    AWS_REGION: str = "us-east-1"
    CONVERSATION_TTL_DAYS: int = 0  # 0 = no TTL

    BEDROCK_EMBEDDING_MODEL: str = "amazon.titan-embed-text-v2:0"
    OPENAPI_SPEC_FETCH_TIMEOUT_SECONDS: float = 15.0
    OPENAPI_LIST_OPERATIONS_TOP_K: int = 20

    @property
    def cors_origins_list(self) -> List[str]:
        if self.CORS_ORIGINS == "*":
            return ["*"]
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


settings = Settings()
