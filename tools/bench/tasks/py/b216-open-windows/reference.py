import re


def open_windows(span: str, booked: list[str]) -> str:
    def minutes(text: str) -> list[int]:
        parts = text.split("-")
        if len(parts) != 2 or any(re.fullmatch(r"\d{2}:\d{2}", p) is None for p in parts):
            raise ValueError("a range must be written HH:MM-HH:MM: " + text)
        return [int(p[:2]) * 60 + int(p[3:]) for p in parts]

    def stamp(at: int) -> str:
        return f"{at // 60:02d}:{at % 60:02d}"

    opening, closing = minutes(span)
    free = []
    cursor = opening
    for start, end in sorted(minutes(entry) for entry in booked):
        if start > cursor:
            free.append(stamp(cursor) + "-" + stamp(start))
        cursor = max(cursor, end)
    if closing > cursor:
        free.append(stamp(cursor) + "-" + stamp(closing))
    return ", ".join(free) if free else "none"
