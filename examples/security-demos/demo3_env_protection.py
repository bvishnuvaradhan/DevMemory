"""DevMemory Demo 3: Environment Variable & Secret Configuration Protection.

Demonstrates DevMemory's behavior when application configuration is missing or malformed,
offering environment troubleshooting steps without exposing sensitive system values.

Usage:
    devmemory run -- python demo3_env_protection.py
"""

import os
import sys


REQUIRED_ENV_VARS = ["DATABASE_URL", "API_SIGNING_SECRET"]


def verify_application_environment() -> None:
    """Verify that required environment variables are present before startup."""
    print("[Demo 3] Checking required production environment variables...")
    missing = [var for var in REQUIRED_ENV_VARS if not os.getenv(var)]
    if missing:
        raise KeyError(
            f"Missing required environment variables: {', '.join(missing)}. "
            f"Please ensure they are defined in your .env or server environment."
        )
    print("[Demo 3] All environment variables verified successfully.")


def main() -> None:
    verify_application_environment()


if __name__ == "__main__":
    main()
