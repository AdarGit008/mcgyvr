def pad_code(code: str, width: int) -> str:
    """A code padded with zeros to a fixed width."""
    return code.rjust(width, "0")
