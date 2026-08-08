import re

BAY = re.compile(r"(\d{1,6})(?:\.(\d{1,4}))?")
PEG = re.compile(r"([A-Za-z])([1-9])")


def tidy_shelf_mark(raw: str) -> str:
    if not isinstance(raw, str):
        raise ValueError("a mark must be a string")
    parts = [part.strip() for part in raw.split("-")]
    if len(parts) != 3:
        raise ValueError("a mark carries exactly three parts")
    wing_raw, bay_raw, peg_raw = parts
    if re.fullmatch(r"[A-Za-z]{2}", wing_raw) is None:
        raise ValueError("the wing is exactly two letters")
    bay_found = BAY.fullmatch(bay_raw)
    if bay_found is None:
        raise ValueError("the bay is misshapen")
    whole = int(bay_found.group(1))
    if whole < 1 or whole > 999:
        raise ValueError("the bay stands between 1 and 999")
    fraction = (bay_found.group(2) or "").rstrip("0")
    if len(fraction) > 2:
        raise ValueError("the fraction is two digits at most")
    peg_found = PEG.fullmatch(peg_raw)
    if peg_found is None:
        raise ValueError("the peg is one letter with one non-zero digit")
    bay = str(whole) if not fraction else str(whole) + "." + fraction
    return (
        wing_raw.upper()
        + "-"
        + bay
        + "-"
        + peg_found.group(1).lower()
        + peg_found.group(2)
    )
