def find_user(users: list[dict[str, int]], user_id: int) -> dict[str, int] | None:
    """Return the first user dict with a matching id, else None."""
    for user in users:
        if user["id"] == user_id:
            return user
    return None
