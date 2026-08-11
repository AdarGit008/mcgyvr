def check_verify(code: str) -> bool:
    total = 0
    for ch in code:
        total += int(ch)
    return total % 10 == 0
