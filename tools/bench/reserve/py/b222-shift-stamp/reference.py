import re

DAY = 24 * 60


def shift_stamp(stamp: str, minutes: int) -> str:
    if not isinstance(stamp, str) or re.fullmatch(r"\d{2}:\d{2}", stamp) is None:
        raise ValueError("a stamp reads as HH:MM")
    hour, minute = int(stamp[:2]), int(stamp[3:])
    if hour > 23 or minute > 59:
        raise ValueError("a stamp names a time of day")
    if isinstance(minutes, bool) or not isinstance(minutes, int):
        raise ValueError("the offset counts whole minutes")
    moved = (hour * 60 + minute + minutes) % DAY
    return f"{moved // 60:02d}:{moved % 60:02d}"
