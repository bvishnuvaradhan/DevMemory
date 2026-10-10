"""DevMemory Demo 1 (Python): Multi-Language Diagnostic Demonstration.

Demonstrates DevMemory's ability to capture Python exceptions, inspect stack traces,
and provide targeted source-aware diagnostics and relevant knowledge base matches.

Usage:
    devmemory run -- python demo1_multilang_py.py
"""

import sys


def calculate_user_quota(base_limit: int, bonus_units: str) -> int:
    """Calculate total quota, intentionally triggering a TypeError."""
    print(f"Calculating quota with base_limit={base_limit} and bonus_units='{bonus_units}'...")
    # Intentional TypeError: cannot add int and str
    total = base_limit + bonus_units
    return total


def main() -> None:
    print("[Demo 1 - Python] Starting quota calculation service...")
    calculate_user_quota(100, "25")


if __name__ == "__main__":
    main()
