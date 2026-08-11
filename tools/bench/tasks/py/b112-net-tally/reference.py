import re


def net_tally(sheets):
    if not isinstance(sheets, list):
        raise ValueError("sheets must be a list")
    sold = {}
    returned = {}
    for sheet in sheets:
        if not isinstance(sheet, str):
            raise ValueError("every sheet must be a string")
        for raw in sheet.split("\n"):
            if raw.strip() == "":
                continue
            fields = [field.strip() for field in raw.split("|")]
            if len(fields) != 3:
                raise ValueError("a row is item|sold|returned")
            item, sold_text, returned_text = fields
            if item == "":
                raise ValueError("item names must be non-empty")
            if not re.fullmatch(r"[0-9]+", sold_text) or not re.fullmatch(
                r"[0-9]+", returned_text
            ):
                raise ValueError("counts must be strings of decimal digits")
            sold[item] = sold.get(item, 0) + int(sold_text)
            returned[item] = returned.get(item, 0) + int(returned_text)
    width = max([len("total")] + [len(item) for item in sold])
    lines = []
    overall = 0
    for item in sorted(sold):
        net = sold[item] - returned.get(item, 0)
        if net < 0:
            raise ValueError("an item's returns exceed its sales")
        overall += net
        lines.append(item.ljust(width) + "  " + str(net))
    if not lines:
        return ""
    lines.append("total".ljust(width) + "  " + str(overall))
    return "\n".join(lines)
