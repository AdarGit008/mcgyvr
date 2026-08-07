def _read_rows(value, what):
    if not isinstance(value, list):
        raise ValueError("the " + what + " must be a list of strings")
    for row in value:
        if not isinstance(row, str):
            raise ValueError("the " + what + " must be a list of strings")
    return list(value)


def mend_row_blocks(rows: list, blocks: list) -> dict:
    sheet = _read_rows(rows, "sheet")
    if not isinstance(blocks, list):
        raise ValueError("the blocks must be a list")
    parsed = []
    for block in blocks:
        if not isinstance(block, dict):
            raise ValueError("every block must be a mapping")
        start = block.get("start")
        if not isinstance(start, int) or isinstance(start, bool) or start < 1:
            raise ValueError("start must be a whole number of one or more")
        drop = block.get("drop")
        if not isinstance(drop, int) or isinstance(drop, bool) or drop < 0:
            raise ValueError("drop must be a whole number of none or more")
        held = block.get("guard")
        if held is not None and not isinstance(held, str):
            raise ValueError("guard must be a string or null")
        parsed.append(
            {
                "start": start,
                "drop": drop,
                "insert": _read_rows(block.get("insert"), "insert"),
                "guard": held,
            }
        )
    for earlier, later in zip(parsed, parsed[1:]):
        if later["start"] <= earlier["start"]:
            raise ValueError("the starts must climb strictly")
        if earlier["start"] + earlier["drop"] > later["start"]:
            raise ValueError("one block reaches into the next")

    out = list(sheet)
    rejected = []
    shift = 0
    for position, block in enumerate(parsed):
        at = block["start"] - 1
        refused = at > len(sheet) or at + block["drop"] > len(sheet)
        if not refused and block["guard"] is not None:
            refused = sheet[at] != block["guard"]
        if refused:
            rejected.append(position)
            continue
        out[at + shift : at + shift + block["drop"]] = block["insert"]
        shift += len(block["insert"]) - block["drop"]
    return {"rows": out, "rejected": rejected}
