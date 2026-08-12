def code_valid(code: str, length: int) -> bool:
    if length <= 0:
        raise ValueError("length must be positive")
    if len(code) != length:
        return False
    allowed = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    for ch in code:
        if ch not in allowed:
            return False
    return True
