import re

SPAN = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
DAY = re.compile(r"\d{4}-\d{2}-\d{2}")


def _span(year: int, month: int) -> int:
    if month != 2:
        return SPAN[month - 1]
    return 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28


def _split(text):
    if not isinstance(text, str) or DAY.fullmatch(text) is None:
        raise ValueError("a day must be written as YYYY-MM-DD")
    year, month, day = int(text[0:4]), int(text[5:7]), int(text[8:10])
    if year < 1900 or year > 2999 or month < 1 or month > 12:
        raise ValueError("a day must be real and lie in 1900 through 2999")
    if day < 1 or day > _span(year, month):
        raise ValueError("a day must be real and lie in 1900 through 2999")
    return year, month, day


def _serial(year: int, month: int, day: int) -> int:
    back = year - 1 if month <= 2 else year
    era = back // 400
    yoe = back - era * 400
    doy = (153 * (month + (-3 if month > 2 else 9)) + 2) // 5 + day - 1
    return era * 146097 + yoe * 365 + yoe // 4 - yoe // 100 + doy - 719468


def _stamp(count: int) -> str:
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


def check_guarantee_claim(sold: str, months: int, grace: int, claim: str) -> dict:
    sy, sm, sd = _split(sold)
    if not isinstance(months, int) or isinstance(months, bool) or months < 1 or months > 240:
        raise ValueError("months must be a whole number from 1 to 240")
    if not isinstance(grace, int) or isinstance(grace, bool) or grace < 0 or grace > 365:
        raise ValueError("grace must be a whole number from 0 to 365")
    cy, cm, cd = _split(claim)

    raw = sm + months
    year = sy + (raw - 1) // 12
    month = (raw - 1) % 12 + 1
    plain = _serial(year, month, min(sd, _span(year, month)))
    last = plain + grace
    start = _serial(sy, sm, sd)
    asked = _serial(cy, cm, cd)

    if asked < start:
        verdict = "early"
    elif asked > last:
        verdict = "lapsed"
    elif asked > plain:
        verdict = "grace"
    else:
        verdict = "inside"
    over = asked - last if verdict == "lapsed" else 0

    return {"plain": _stamp(plain), "last": _stamp(last), "verdict": verdict, "over": over}
