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
    # Hypertide uses email/password authentication
    auth_email: Optional[str] = Field(default=None)
    auth_password: Optional[str] = Field(default=None)
    session_storage_path: Path = Field(
        default=Path("~/.hypertide/session").expanduser()
    )

    # Auto-login settings
    login_timeout: int = Field(default=30000, description="Timeout for login form submission")

    # Browser settings
    headless: bool = Field(default=False, description="Run browser in headless mode")
    slow_mo: int = Field(default=100, description="Slow down operations by ms (for debugging)")
    timeout: int = Field(default=60000, description="Default timeout in ms (increased for Docker)")

    # Per-operation timeouts (ms)
    navigation_timeout: int = Field(default=90000, description="Timeout for page navigation")
    element_timeout: int = Field(default=30000, description="Timeout for element interactions")
    auth_check_timeout: int = Field(default=45000, description="Timeout for auth verification")

    # Screenshots
    screenshot_on_error: bool = Field(default=True)
    screenshot_dir: Path = Field(default=Path("./screenshots"))

    # Retry settings
    max_retries: int = Field(default=3)
    retry_delay: int = Field(default=3000, description="Initial delay between retries in ms")
    retry_backoff: float = Field(default=1.5, description="Exponential backoff multiplier")

    @classmethod
    def from_env(cls) -> "HypertideConfig":
        """Load configuration from environment variables."""
        return cls(
            auth_email=os.getenv("HYPERTIDE_EMAIL"),
            auth_password=os.getenv("HYPERTIDE_PASSWORD"),
            headless=os.getenv("HYPERTIDE_HEADLESS", "false").lower() == "true",
            slow_mo=int(os.getenv("HYPERTIDE_SLOW_MO", "100")),
            timeout=int(os.getenv("HYPERTIDE_TIMEOUT", "60000")),
            navigation_timeout=int(os.getenv("HYPERTIDE_NAVIGATION_TIMEOUT", "90000")),
            element_timeout=int(os.getenv("HYPERTIDE_ELEMENT_TIMEOUT", "30000")),
            auth_check_timeout=int(os.getenv("HYPERTIDE_AUTH_CHECK_TIMEOUT", "45000")),
            login_timeout=int(os.getenv("HYPERTIDE_LOGIN_TIMEOUT", "30000")),
            max_retries=int(os.getenv("HYPERTIDE_MAX_RETRIES", "3")),
            retry_delay=int(os.getenv("HYPERTIDE_RETRY_DELAY", "3000")),
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
