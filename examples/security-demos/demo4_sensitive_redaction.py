"""DevMemory Demo 4: Sensitive Secret Redaction & Privacy Demonstration.

Demonstrates DevMemory's automatic, strict redaction of sensitive credentials,
synthetic API keys, database connection strings, and tokens from command execution
logs, terminal summaries, and stored backend incident payloads.

Usage:
    devmemory run -- python demo4_sensitive_redaction.py
"""

import sys


def run_database_migration() -> None:
    """Simulate a database connection failure that prints raw connection credentials."""
    print("[Demo 4] Connecting to remote cluster...")
    # Synthetic/mock credentials used exclusively for testing redaction guards
    dummy_conn_uri = "mongodb://cluster_admin:SuperSecretPassword999@mongodb.example.net:27017/prod_db"
    dummy_api_key = "sk-live-DEMO1234567890abcdef1234567890"
    dummy_github_token = "ghp_DEMO00000000000000000000000000000000"

    sys.stderr.write(
        f"DatabaseConnectionError: Authentication failed for connection URI: {dummy_conn_uri}\n"
        f"Failed using client API key: {dummy_api_key} and authorization token: {dummy_github_token}\n"
        f"Service aborting execution.\n"
    )
    sys.exit(1)


def main() -> None:
    print("[Demo 4] Initiating secure data migration workflow...")
    run_database_migration()


if __name__ == "__main__":
    main()
