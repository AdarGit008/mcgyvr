import re

SPOT = re.compile(r"[a-z][a-z0-9_]*$")


def _spot_name(text: str) -> str:
    if not text.startswith(".") or SPOT.fullmatch(text[1:]) is None:
        raise ValueError(f"badly spelled spot: {text}")
    return text[1:]


def emit_corla_bytes(lines: list[str]) -> list[int]:
    if not isinstance(lines, list):
        raise ValueError("emit_corla_bytes expects a list of rows")
    spots: dict[str, int] = {}
    steps: list[tuple[int, int, int, str | None]] = []
    tally = 0
    for raw in lines:
        if not isinstance(raw, str):
            raise ValueError("every row must be text")
        row = raw.strip()
        if row == "" or row.startswith("#"):
            continue
        if row.startswith("."):
            name = _spot_name(row)
            if name in spots:
                raise ValueError(f"spot named twice: {name}")
            spots[name] = tally
            continue
        parts = row.split()
        keyword = parts[0]
        if keyword in ("NOP", "STOP"):
            if len(parts) != 1:
                raise ValueError(f"wrong count of arguments: {row}")
            steps.append((0 if keyword == "NOP" else 64, 1, 0, None))
            tally += 1
        elif keyword == "LOAD":
            if len(parts) != 2:
                raise ValueError(f"wrong count of arguments: {row}")
            if re.fullmatch(r"0|[1-9][0-9]*", parts[1]) is None or int(parts[1]) > 255:
                raise ValueError(f"v outside 0 to 255: {parts[1]}")
            steps.append((16, 2, int(parts[1]), None))
            tally += 2
        elif keyword in ("GOTO", "CALL"):
            if len(parts) != 2:
                raise ValueError(f"wrong count of arguments: {row}")
            code = 32 if keyword == "GOTO" else 48
            steps.append((code, 3, 0, _spot_name(parts[1])))
            tally += 3
        else:
            raise ValueError(f"keyword nobody knows: {row}")
    out: list[int] = []
    for code, width, value, spot in steps:
        if spot is None:
            out.append(code)
            if width == 2:
                out.append(value)
            continue
        if spot not in spots:
            raise ValueError(f"no row names spot: {spot}")
        seat = spots[spot]
        out.extend([code, seat // 256, seat % 256])
    return out
