"""
Configuration settings for Charm Email OS API
Loads from environment variables
"""

import json
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment"""

    # Database Configuration (OwnRBL PostgreSQL)
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "postgres"
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = ""
    POSTGRES_SCHEMA: str = "public"

    # Email Bison API (optional, for direct API calls)
    EMAILBISON_API_KEY: str = ""
    EMAILBISON_API_URL: str = "https://spellcast.hirecharm.com"

    # API Configuration
    API_TITLE: str = "Charm Email OS API"
    API_VERSION: str = "1.0.0"
    API_PREFIX: str = "/api"
    DEBUG: bool = False

    # CORS Configuration - stored as string, parsed by property
    CORS_ORIGINS_RAW: str = "*"

    @property
    def CORS_ORIGINS(self) -> list[str]:
        """Parse CORS_ORIGINS from string"""
        v = self.CORS_ORIGINS_RAW
        # Try parsing as JSON first
        if v.startswith('['):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                pass
        # Fall back to comma-separated or single value
        return [origin.strip() for origin in v.split(',') if origin.strip()]

    @property
    def database_url(self) -> str:
        """Construct async PostgreSQL connection URL"""
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    @property
    def database_url_sync(self) -> str:
        """Construct sync PostgreSQL connection URL (for migrations)"""
        return f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    """Cached settings instance"""
    return Settings()


settings = get_settings()
