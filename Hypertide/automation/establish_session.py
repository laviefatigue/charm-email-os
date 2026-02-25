"""
One-time script to establish Hypertide session.
Run this locally with a visible browser to login manually.
Session will be saved to ~/.hypertide/session for future headless use.
"""
import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from hypertide_automation.client import HypertideClient
from hypertide_automation.config import HypertideConfig

async def establish_session():
    print("=" * 60)
    print("HYPERTIDE SESSION ESTABLISHMENT")
    print("=" * 60)
    print()
    print("This will open a Chrome browser window.")
    print("Please login to Hypertide when the browser opens.")
    print("The session will be saved for future headless automation.")
    print()
    print("Session will be saved to: ~/.hypertide/session")
    print()

    # Create config with visible browser
    config = HypertideConfig(headless=False, slow_mo=100)
    client = HypertideClient(config)

    try:
        print("Starting browser...")
        await client.start()

        print("Checking authentication status...")
        if await client.is_authenticated():
            print("Already authenticated! Session is valid.")
        else:
            print()
            print("=" * 60)
            print("PLEASE LOGIN IN THE BROWSER WINDOW")
            print("Waiting for you to complete login...")
            print("(Timeout: 5 minutes)")
            print("=" * 60)
            print()

            await client.ensure_authenticated()
            print("Login successful!")

        # Save session
        await client.save_session()

        session_path = config.session_storage_path
        print()
        print("=" * 60)
        print("SESSION ESTABLISHED SUCCESSFULLY!")
        print(f"Saved to: {session_path}")
        print()
        print("You can now copy this file to your server:")
        print(f"  scp {session_path} root@31.97.142.123:/root/.hypertide/session")
        print("=" * 60)

    except Exception as e:
        print(f"Error: {e}")
        raise
    finally:
        await client.close()

if __name__ == "__main__":
    asyncio.run(establish_session())
