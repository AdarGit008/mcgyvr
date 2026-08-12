def ordinal_of(value: int) -> str:
    if value % 100 in (11, 12, 13):
        return str(value) + "th"
    last = value % 10
    if last == 1:
        return str(value) + "st"
    if last == 2:
        return str(value) + "nd"
    if last == 3:
        return str(value) + "rd"
    return str(value) + "th"
