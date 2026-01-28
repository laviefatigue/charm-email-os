"""
Hypertide session initialization.
Decodes the HYPERTIDE_SESSION_B64 environment variable and saves it to the session file.
This runs on API startup to ensure the session is available for Hypertide automation.
"""
import os
import base64
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

SESSION_PATH = Path.home() / ".hypertide" / "session"


def init_hypertide_session():
    """
    Initialize Hypertide session from environment variable.

    If HYPERTIDE_SESSION_B64 is set, decode it and save to ~/.hypertide/session.
    This allows the session to be passed to the container via environment variable
    without needing SSH access or volume mounts.
    """
    session_b64 = os.getenv("HYPERTIDE_SESSION_B64")

    if not session_b64:
        logger.debug("HYPERTIDE_SESSION_B64 not set, skipping session initialization")
        return False

    # Check if session already exists and is non-empty
    if SESSION_PATH.exists() and SESSION_PATH.stat().st_size > 0:
        logger.info(f"Hypertide session already exists at {SESSION_PATH}")
        return True

    try:
        # Decode base64 session
        session_data = base64.b64decode(session_b64)

        # Ensure directory exists
        SESSION_PATH.parent.mkdir(parents=True, exist_ok=True)

        # Write session file
        SESSION_PATH.write_bytes(session_data)

        logger.info(f"Hypertide session initialized at {SESSION_PATH} ({len(session_data)} bytes)")
        return True

    except Exception as e:
        logger.error(f"Failed to initialize Hypertide session: {e}")
        return False


if __name__ == "__main__":
    # Test the initialization
    logging.basicConfig(level=logging.INFO)
    init_hypertide_session()
