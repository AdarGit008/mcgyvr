def _whole(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _label(value):
    return isinstance(value, str) and bool(value)


def audit_swap_board(board: dict, ceiling: int) -> dict:
    if not _whole(ceiling) or ceiling < 1:
        raise ValueError("the ceiling is not whole or falls below one")
    if not isinstance(board, dict):
        raise ValueError("the board is not a record")
    if sorted(board) != ["claims", "shifts"]:
        raise ValueError("the board's keys are not exactly shifts and claims")

    shifts = board["shifts"]
    if not isinstance(shifts, list):
        raise ValueError("the shifts are not a list")
    days = {}
    holders = {}
    for shift in shifts:
        if not isinstance(shift, dict):
            raise ValueError("a shift is not a record")
        if sorted(shift) != ["code", "day", "holder"]:
            raise ValueError("a shift's keys are not exactly the three named")
        if not _label(shift["code"]):
            raise ValueError("a code is not a non-empty string")
        if shift["code"] in holders:
            raise ValueError("two shifts carry one code")
        day = shift["day"]
        if not _whole(day) or day < 1 or day > 7:
            raise ValueError("a day is not whole or falls outside one through seven")
        if not _label(shift["holder"]):
            raise ValueError("a holder is not a non-empty string")
        days[shift["code"]] = day
        holders[shift["code"]] = shift["holder"]

    claims = board["claims"]
    if not isinstance(claims, list):
        raise ValueError("the claims are not a list")
    for claim in claims:
        if not isinstance(claim, dict):
            raise ValueError("a claim is not a record")
        if sorted(claim) != ["bidder", "code"]:
            raise ValueError("a claim's keys are not exactly code and bidder")
        if not _label(claim["code"]):
            raise ValueError("a claimed code is not a non-empty string")
        if not _label(claim["bidder"]):
            raise ValueError("a bidder is not a non-empty string")

    moved = set()
    verdicts = []

    for claim in claims:
        code = claim["code"]
        bidder = claim["bidder"]
        if code not in holders:
            verdicts.append("unknown")
            continue
        if code in moved:
            verdicts.append("gone")
            continue
        if holders[code] == bidder:
            verdicts.append("self")
            continue
        clash = False
        load = 0
        for other, who in holders.items():
            if who != bidder:
                continue
            load += 1
            if days[other] == days[code]:
                clash = True
        if clash:
            verdicts.append("busy")
            continue
        if load >= ceiling:
            verdicts.append("full")
            continue
        holders[code] = bidder
        moved.add(code)
        verdicts.append("taken")

    counts = {}
    for who in holders.values():
        counts[who] = counts.get(who, 0) + 1
    loads = [f"{who} {counts[who]}" for who in sorted(counts)]

    return {"verdicts": verdicts, "loads": loads}
