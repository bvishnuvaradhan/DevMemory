"""DevMemory Demo 2: Input Validation and Schema Parsing Demonstration.

Demonstrates DevMemory's capture of runtime validation errors (ValueError / JSONDecodeError)
and retrieval of actionable troubleshooting guidance.

Usage:
    devmemory run -- python demo2_invalid_input.py
"""

import json
import sys


def parse_service_payload(raw_data: str) -> dict:
    """Parse JSON configuration payload and validate required fields."""
    print("[Demo 2] Validating incoming JSON payload...")
    data = json.loads(raw_data)
    if "port" not in data:
        raise ValueError("Invalid configuration: missing required integer field 'port'")
    return data


def main() -> None:
    # Malformed JSON payload missing closing brace and required field
    malformed_payload = '{"service": "auth-api", "host": "127.0.0.1"'
    print("[Demo 2] Submitting unclosed payload for processing...")
    parse_service_payload(malformed_payload)


if __name__ == "__main__":
    main()
