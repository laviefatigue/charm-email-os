"""
Configuration settings for Charm Email OS API
Loads from environment variables
"""

import os
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

    # CORS Configuration
    CORS_ORIGINS: list[str] = ["*"]

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
