"""Environment-driven configuration. Hard fail if a required value is missing."""
from __future__ import annotations

import os
from dataclasses import dataclass


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class Config:
    database_url: str
    hypertide_api_key: str
    hypertide_api_url: str

    @classmethod
    def from_env(cls) -> Config:
        missing = []
        db = os.getenv("DATABASE_URL", "")
        if not db:
            missing.append("DATABASE_URL")
        ht_key = os.getenv("HYPERTIDE_API_KEY", "")
        if not ht_key:
            missing.append("HYPERTIDE_API_KEY")
        if missing:
            raise ConfigError(
                f"Missing required environment variables: {', '.join(missing)}"
            )
        ht_url = os.getenv("HYPERTIDE_API_URL", "https://backend.hypertide.io").rstrip("/")
        # Normalize: accept with or without /api/v1 suffix.
        if not ht_url.endswith("/api/v1"):
            ht_url = f"{ht_url}/api/v1"
        return cls(
            database_url=db,
            hypertide_api_key=ht_key,
            hypertide_api_url=ht_url,
        )
