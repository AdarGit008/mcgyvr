def cloud_code(table: dict, code: str) -> str:
    key = code.upper()
    if key in table:
        return table[key]
    return "unknown"
