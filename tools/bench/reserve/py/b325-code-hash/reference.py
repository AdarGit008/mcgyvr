def code_hash(code: str, buckets: int) -> int:
    if buckets <= 0:
        raise ValueError("buckets must be positive")
    total = 0
    for letter in code.lower():
        if "a" <= letter <= "z":
            total += ord(letter) - 96
    return total % buckets
