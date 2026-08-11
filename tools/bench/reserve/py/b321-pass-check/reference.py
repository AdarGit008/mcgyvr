def pass_check(phrase: str) -> bool:
    if len(phrase) < 8:
        return False
    digits = "0123456789"
    letters = "abcdefghijklmnopqrstuvwxyz"
    has_digit = any(ch in digits for ch in phrase)
    has_letter = any(ch.lower() in letters for ch in phrase)
    return has_digit and has_letter
