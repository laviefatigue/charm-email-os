"""
Configuration management for Hypertide automation.
"""

import os
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class HypertideConfig(BaseModel):
    """Configuration for Hypertide automation."""

    # URLs
    base_url: str = Field(default="https://app2.hypertide.io")
    signin_url: str = Field(default="https://app2.hypertide.io/signin")
    dashboard_url: str = Field(default="https://app2.hypertide.io/dashboard")
    choose_plan_url: str = Field(default="https://app2.hypertide.io/choose-plan")

    # Authentication
    # Note: Hypertide uses OAuth/magic link - we'll use persistent browser context
    auth_email: Optional[str] = Field(default=None)
    session_storage_path: Path = Field(
        default=Path("~/.hypertide/session").expanduser()
    )

    # Browser settings
    headless: bool = Field(default=False, description="Run browser in headless mode")
    slow_mo: int = Field(default=100, description="Slow down operations by ms (for debugging)")
    timeout: int = Field(default=30000, description="Default timeout in ms")

    # Screenshots
    screenshot_on_error: bool = Field(default=True)
    screenshot_dir: Path = Field(default=Path("./screenshots"))

    # Retry settings
    max_retries: int = Field(default=3)
    retry_delay: int = Field(default=2000, description="Delay between retries in ms")

    @classmethod
    def from_env(cls) -> "HypertideConfig":
        """Load configuration from environment variables."""
        return cls(
            auth_email=os.getenv("HYPERTIDE_EMAIL"),
            headless=os.getenv("HYPERTIDE_HEADLESS", "false").lower() == "true",
            slow_mo=int(os.getenv("HYPERTIDE_SLOW_MO", "100")),
            timeout=int(os.getenv("HYPERTIDE_TIMEOUT", "30000")),
        )


class StripeConfig(BaseModel):
    """Configuration for Stripe payment handling."""

    # If you have saved payment methods, the checkout should auto-select
    use_saved_payment: bool = Field(default=True)

    # Timeout for Stripe checkout iframe
    checkout_timeout: int = Field(default=60000, description="Stripe checkout timeout in ms")

    # Wait for confirmation
    confirmation_timeout: int = Field(default=30000)


# Global config instance
_config: Optional[HypertideConfig] = None


def get_config() -> HypertideConfig:
    """Get or create the global configuration."""
    global _config
    if _config is None:
        _config = HypertideConfig.from_env()
    return _config


def set_config(config: HypertideConfig) -> None:
    """Set the global configuration."""
    global _config
    _config = config
