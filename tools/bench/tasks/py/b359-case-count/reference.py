def case_count(text: str) -> list:
    upper = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    lower = "abcdefghijklmnopqrstuvwxyz"
    capitals = 0
    smalls = 0
    for ch in text:
        if ch in upper:
            capitals += 1
        elif ch in lower:
            smalls += 1
    return [capitals, smalls]
