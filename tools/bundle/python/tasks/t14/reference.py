def select_active(users: list[dict]) -> list[str]:
    """Names of active adult users."""
    return [u["name"] for u in users if u["active"] and u["age"] >= 18]
