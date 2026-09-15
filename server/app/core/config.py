"""Application configuration management.

This module handles environment-specific configuration loading, parsing, and management
for the application. It includes environment detection, .env file loading, and
configuration value parsing using Pydantic Settings for type safety and validation.
"""

import os
from enum import Enum
from pathlib import Path
from typing import List

from pydantic import (
    Field,
    SecretStr,
    field_validator,
)
from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict,
)


# Define environment types
class Environment(str, Enum):
    """Application environment types.

    Defines the possible environments the application can run in:
    development, staging, production, and test.
    """

    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TEST = "test"


# Determine environment
def get_environment() -> Environment:
    """Get the current environment.

    Returns:
        Environment: The current environment (development, staging, production, or test)
    """
    match os.getenv("APP_ENV", "development").lower():
        case "production" | "prod":
            return Environment.PRODUCTION
        case "staging" | "stage":
            return Environment.STAGING
        case "test":
            return Environment.TEST
        case _:
            return Environment.DEVELOPMENT


# Database Settings
class DatabaseSettings(BaseSettings):
    """PostgreSQL database configuration."""

    model_config = SettingsConfigDict(env_prefix="POSTGRES_")

    HOST: str = "localhost"
    PORT: int = 5432
    DB: str = "food_order_db"
    USER: str = "postgres"
    PASSWORD: SecretStr = Field(default=SecretStr("postgres"))
    POOL_SIZE: int = 15
    MAX_OVERFLOW: int = 5
    CHECKPOINT_TABLES: List[str] = Field(
        default_factory=lambda: ["checkpoint_blobs", "checkpoint_writes", "checkpoints"]
    )


# Langfuse Settings
class LangfuseSettings(BaseSettings):
    """Langfuse observability configuration."""

    model_config = SettingsConfigDict(env_prefix="LANGFUSE_")

    PUBLIC_KEY: SecretStr = Field(default=SecretStr(""))
    SECRET_KEY: SecretStr = Field(default=SecretStr(""))
    HOST: str = "https://cloud.langfuse.com"


# LLM Settings
class LLMSettings(BaseSettings):
    """LLM and LangGraph configuration."""

    model_config = SettingsConfigDict(env_prefix="")

    OPENAI_API_KEY: SecretStr = Field(default=SecretStr(""))
    DEFAULT_LLM_MODEL: str = "gpt-5-mini"
    DEFAULT_LLM_TEMPERATURE: float = 0.2
    MAX_TOKENS: int = 2000
    MAX_LLM_CALL_RETRIES: int = 3


# Long-term Memory Settings
class MemorySettings(BaseSettings):
    """Long-term memory configuration using mem0ai."""

    model_config = SettingsConfigDict(env_prefix="LONG_TERM_MEMORY_")

    MODEL: str = "gpt-5-nano"
    EMBEDDER_MODEL: str = "text-embedding-3-small"
    COLLECTION_NAME: str = "longterm_memory"

    # Retrieval breadth for `get_relevant_memory`. Every hit is rendered into
    # the agent's prompt, so these bound prompt size as much as they bound
    # recall. They restate mem0 2.0's own defaults on purpose: 2.0 already
    # changed both under us (limit 100 -> top_k 20, threshold None -> 0.1),
    # and passing them explicitly is what stops the next flip from silently
    # resizing that block of prompt.
    SEARCH_TOP_K: int = 20
    SEARCH_THRESHOLD: float = 0.1


# Clerk Authentication Settings
class AuthSettings(BaseSettings):
    """Clerk authentication configuration."""

    model_config = SettingsConfigDict(env_prefix="CLERK_")

    SECRET_KEY: SecretStr = Field(default=SecretStr(""))
    # Per-endpoint signing secret from the Clerk dashboard (whsec_...).
    # Enforced at container start by REQUIRED_ENV_VARS in
    # scripts/docker-entrypoint.sh, NOT by making this field required:
    # alembic/env.py imports this module, so a required field would force the
    # one-shot migrate service to carry a secret it never uses and would
    # defeat its deliberate REQUIRED_ENV_VARS= opt-out.
    WEBHOOK_SIGNING_SECRET: SecretStr = Field(default=SecretStr(""))
    ISSUER: str = ""
    OAUTH_CLIENT_ID: str = ""
    AUTHORIZE_URL: str = ""
    TOKEN_URL: str = ""

    @property
    def jwks_url(self) -> str:
        """Derive JWKS URL from issuer."""
        return f"{self.ISSUER}/.well-known/jwks.json"


# Logging Settings
class LoggingSettings(BaseSettings):
    """Logging configuration."""

    model_config = SettingsConfigDict(env_prefix="LOG_")

    DIR: Path = Field(default=Path("logs"))
    LEVEL: str = "INFO"
    FORMAT: str = "json"  # "json" or "console"

    @field_validator("DIR", mode="before")
    @classmethod
    def ensure_path(cls, v):
        """Convert string to Path and create directory if needed."""
        if isinstance(v, str):
            v = Path(v)
        # Create directory if it doesn't exist
        if isinstance(v, Path):
            v.mkdir(parents=True, exist_ok=True)
        return v


# Rate Limit Endpoint Settings
class RateLimitEndpointSettings(BaseSettings):
    """Rate limit configuration for individual endpoints."""

    model_config = SettingsConfigDict(env_prefix="RATE_LIMIT_")

    CHAT: List[str] = Field(default_factory=lambda: ["30 per minute"])
    CHAT_STREAM: List[str] = Field(default_factory=lambda: ["20 per minute"])
    MESSAGES: List[str] = Field(default_factory=lambda: ["50 per minute"])
    REGISTER: List[str] = Field(default_factory=lambda: ["10 per hour"])
    LOGIN: List[str] = Field(default_factory=lambda: ["20 per minute"])
    ROOT: List[str] = Field(default_factory=lambda: ["10 per minute"])
    HEALTH: List[str] = Field(default_factory=lambda: ["60 per minute"])
    READY: List[str] = Field(default_factory=lambda: ["10 per minute"])


# Rate Limit Settings
class RateLimitSettings(BaseSettings):
    """Rate limiting configuration."""

    model_config = SettingsConfigDict(env_prefix="RATE_LIMIT_")

    DEFAULT: List[str] = Field(default_factory=lambda: ["200 per day", "50 per hour"])
    endpoints: RateLimitEndpointSettings = Field(default_factory=RateLimitEndpointSettings)


# Evaluation Settings
class EvaluationSettings(BaseSettings):
    """LLM evaluation configuration."""

    model_config = SettingsConfigDict(env_prefix="EVALUATION_")

    LLM: str = "gpt-5"
    BASE_URL: str = "https://api.openai.com/v1"
    API_KEY: SecretStr = Field(default=SecretStr(""))
    SLEEP_TIME: int = 10

    @field_validator("API_KEY", mode="before")
    @classmethod
    def default_to_openai_key(cls, v):
        """Default to OPENAI_API_KEY if EVALUATION_API_KEY not set."""
        if not v or v == "":
            return os.getenv("OPENAI_API_KEY", "")
        return v


# CORS Settings
class CORSSettings(BaseSettings):
    """CORS configuration."""

    model_config = SettingsConfigDict(env_prefix="")

    ALLOWED_ORIGINS: List[str] = Field(default_factory=list)


# Main Settings Class
class Settings(BaseSettings):
    """Main application settings with nested configuration models.

    This class uses Pydantic Settings for type-safe configuration management,
    automatic validation, and loading from environment variables and .env files.
    All settings are organized into nested models by domain (database, auth, etc.)
    """

    model_config = SettingsConfigDict(
        env_file=f".env.{get_environment().value}",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Environment
    ENVIRONMENT: Environment = Field(default_factory=get_environment)

    # Application Settings.
    # The service's name, version, description and versioned path prefix are NOT
    # here: they are product identity and published interface rather than
    # deployment configuration, and an env-overridable title or route prefix
    # would make the exported OpenAPI artifact differ per machine. See
    # app/core/metadata.py.
    DEBUG: bool = False

    # Nested Settings
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    langfuse: LangfuseSettings = Field(default_factory=LangfuseSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    memory: MemorySettings = Field(default_factory=MemorySettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    rate_limits: RateLimitSettings = Field(default_factory=RateLimitSettings)
    evaluation: EvaluationSettings = Field(default_factory=EvaluationSettings)
    cors: CORSSettings = Field(default_factory=CORSSettings)


# Create settings instance
settings = Settings()
