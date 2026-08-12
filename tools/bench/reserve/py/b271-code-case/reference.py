def code_case(code: str) -> str:
    tidy = code.strip()
    if not tidy:
        raise ValueError("empty code")
    return tidy.upper()
