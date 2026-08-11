def check_digit(code: str) -> int:
    total = 0
    for ch in code:
        if not ch.isdigit():
            raise ValueError("not a digit: " + ch)
        total += int(ch)
    return (10 - total % 10) % 10
