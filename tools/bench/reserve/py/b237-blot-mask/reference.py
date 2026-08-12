def blot_mask(code: str) -> str:
    if len(code) <= 4:
        return code
    return "*" * (len(code) - 4) + code[-4:]
