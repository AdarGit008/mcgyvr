def normalize_part_code(code: str) -> str:
    if not isinstance(code, str):
        raise ValueError("normalize_part_code expects a string")
    cleaned = ""
    for ch in code:
        if ch in " -":
            continue
        upper = ch.upper()
        if len(upper) != 1 or not ("0" <= upper <= "9" or "A" <= upper <= "Z"):
            raise ValueError(f"invalid character {ch!r}")
        cleaned += upper
    if len(cleaned) != 9:
        raise ValueError("expected nine characters after cleaning")

    def value(ch: str) -> int:
        return int(ch, 36)

    weights = [3, 5, 7, 3, 5, 7, 3, 5]
    checksum = sum(value(ch) * w for ch, w in zip(cleaned[:8], weights)) % 36
    if value(cleaned[8]) != checksum:
        raise ValueError("check character does not verify")
    return f"{cleaned[:4]}-{cleaned[4:8]}-{cleaned[8]}"
