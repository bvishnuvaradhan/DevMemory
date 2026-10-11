"""
Deterministic Python failure fixture for DevMemory end-to-end testing.
Throws a ZeroDivisionError with explicit stack depth.
"""

def compute_ratio(numerator: float, denominator: float) -> float:
    # Explicit failing operation on line 8
    return numerator / denominator


def process_transaction(account_id: str, balance: float, units: int) -> float:
    print(f"Processing transaction for account: {account_id}")
    return compute_ratio(balance, units)


if __name__ == "__main__":
    process_transaction("ACC-90210", 1500.0, 0)
