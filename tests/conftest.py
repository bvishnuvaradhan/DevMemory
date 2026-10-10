"""Root pytest configuration and environment setup.

Ensures application configuration and local .env files are initialized
for test sessions without overriding existing environment variables.
"""

import os
from pathlib import Path

try:
    from app.config import get_settings

    # Initialize settings and load local .env into os.environ if present
    get_settings()
except Exception:
    pass
