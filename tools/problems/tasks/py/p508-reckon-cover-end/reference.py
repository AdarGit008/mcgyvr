import re

LENGTHS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def _leap(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def _month_length(year: int, month: int) -> int:
    return 29 if month == 2 and _leap(year) else LENGTHS[month - 1]


def _parse(text):
    if not isinstance(text, str) or DATE.fullmatch(text) is None:
        raise ValueError("a date must be written as YYYY-MM-DD")
    year, month, day = int(text[0:4]), int(text[5:7]), int(text[8:10])
    if year < 1900 or year > 2999 or month < 1 or month > 12:
        raise ValueError("a date must name a real month in 1900 through 2999")
    if day < 1 or day > _month_length(year, month):
        raise ValueError("a date must name a day that exists in its month")
    return year, month, day


def _to_days(year: int, month: int, day: int) -> int:
    shifted = year - 1 if month <= 2 else year
    era = shifted // 400
    yoe = shifted - era * 400
    doy = (153 * (month + (-3 if month > 2 else 9)) + 2) // 5 + day - 1
    doe = yoe * 365 + yoe // 4 - yoe // 100 + doy
    return era * 146097 + doe - 719468


def _from_days(count: int) -> str:
    shifted = count + 719468
    era = shifted // 146097
    doe = shifted - era * 146097
    yoe = (doe - doe // 1460 + doe // 36524 - doe // 146096) // 365
    year = yoe + era * 400
    doy = doe - (365 * yoe + yoe // 4 - yoe // 100)
    mp = (5 * doy + 2) // 153
    day = doy - (153 * mp + 2) // 5 + 1
    month = mp + (3 if mp < 10 else -9)
    full = year + 1 if month <= 2 else year
    return "%04d-%02d-%02d" % (full, month, day)


def _whole(value, low: int, high: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and low <= value <= high


def reckon_cover_end(policy: dict) -> dict:
    if not isinstance(policy, dict):
        raise ValueError("the policy must be a mapping")
    by, bm, bd = _parse(policy.get("bought"))
    bought = _to_days(by, bm, bd)
    if not _whole(policy.get("months"), 1, 120):
        raise ValueError("months must be a whole number from 1 to 120")
    extensions = policy.get("extensions")
    if not isinstance(extensions, list):
        raise ValueError("the extensions must be a list")
    total = policy["months"]
    for extra in extensions:
        if not _whole(extra, 1, 60):
            raise ValueError("an extension must be a whole number from 1 to 60")
        total += extra

    repairs = policy.get("repairs")
    if not isinstance(repairs, list):
        raise ValueError("the repairs must be a list")
    suspended = 0
    previous = -1
    for repair in repairs:
        if not isinstance(repair, dict):
            raise ValueError("a repair must be a mapping")
        opened = _to_days(*_parse(repair.get("in")))
        closed = _to_days(*_parse(repair.get("out")))
        if closed < opened:
            raise ValueError("a repair may not close before it opens")
        if opened < bought:
            raise ValueError("a repair may not open before the purchase")
        if previous >= 0 and opened <= previous:
            raise ValueError("the repairs must stand apart and in opening order")
        previous = closed
        suspended += closed - opened + 1

    raw = bm + total
    year = by + (raw - 1) // 12
    month = (raw - 1) % 12 + 1
    day = min(bd, _month_length(year, month))
    ends = _to_days(year, month, day) + suspended

    claim = _to_days(*_parse(policy.get("claim")))
    if claim < bought:
        verdict = "early"
    elif claim > ends:
        verdict = "lapsed"
    else:
        verdict = "covered"
    left = ends - claim + 1 if verdict == "covered" else 0

    return {"ends": _from_days(ends), "suspended": suspended, "verdict": verdict, "left": left}
