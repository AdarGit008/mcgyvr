def _whole(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _read_rows(rows, side):
    if not isinstance(rows, list):
        raise ValueError(f"the {side} must be a list of rows")
    seen = set()
    out = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError(f"a {side} row must be a record")
        for field in ("ref", "day", "cents"):
            if field not in row:
                raise ValueError(f"a {side} row is missing {field}")
        ref = row["ref"]
        day = row["day"]
        cents = row["cents"]
        if not isinstance(ref, str) or ref == "":
            raise ValueError(f"a {side} ref must be a non-empty string")
        if not _whole(day):
            raise ValueError(f"{ref} has a day that is not a whole number")
        if not _whole(cents):
            raise ValueError(f"{ref} has cents that are not a whole number")
        if cents == 0:
            raise ValueError(f"{ref} moves no money")
        if ref in seen:
            raise ValueError(f"the {side} repeats {ref}")
        seen.add(ref)
        out.append({"ref": ref, "day": day, "cents": cents})
    return out


def match_statement_rows(book: list[dict], bank: list[dict], tolerance: int) -> dict:
    book_rows = _read_rows(book, "cash book")
    bank_rows = _read_rows(bank, "bank statement")
    if not _whole(tolerance) or tolerance < 0:
        raise ValueError("the tolerance must be a whole number of days, not negative")

    walk = sorted(book_rows, key=lambda row: (row["day"], row["ref"]))
    taken = set()
    pairs = []
    book_only = []
    for row in walk:
        best = None
        best_key = None
        for candidate in bank_rows:
            if candidate["ref"] in taken or candidate["cents"] != row["cents"]:
                continue
            gap = abs(candidate["day"] - row["day"])
            if gap > tolerance:
                continue
            key = (gap, candidate["day"], candidate["ref"])
            if best_key is None or key < best_key:
                best = candidate
                best_key = key
        if best is None:
            book_only.append(row["ref"])
        else:
            taken.add(best["ref"])
            pairs.append([row["ref"], best["ref"]])
    bank_only = sorted(row["ref"] for row in bank_rows if row["ref"] not in taken)
    return {"pairs": pairs, "bookOnly": sorted(book_only), "bankOnly": bank_only}
