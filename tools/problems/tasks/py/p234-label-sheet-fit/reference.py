def _whole(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _positive(record, key):
    value = record.get(key)
    if not _whole(value) or value < 1:
        raise ValueError(key + " must be a positive integer")
    return value


def _offset(record, key):
    value = record.get(key)
    if not _whole(value) or value < 0:
        raise ValueError(key + " must be a non-negative integer")
    return value


def _along(field, size, gap):
    if field < size:
        return 0
    return (field + gap) // (size + gap)


def fit_label_sheet(sheet: dict, label: dict) -> dict:
    if not isinstance(sheet, dict):
        raise ValueError("the sheet must be a record")
    if not isinstance(label, dict):
        raise ValueError("the label must be a record")
    sheet_width = _positive(sheet, "width")
    sheet_height = _positive(sheet, "height")
    margin_x = _offset(sheet, "marginX")
    margin_y = _offset(sheet, "marginY")
    gap_x = _offset(sheet, "gapX")
    gap_y = _offset(sheet, "gapY")
    label_width = _positive(label, "width")
    label_height = _positive(label, "height")
    if not isinstance(label.get("turn"), bool):
        raise ValueError("turn must be a boolean")

    field_width = sheet_width - 2 * margin_x
    field_height = sheet_height - 2 * margin_y

    grids = []
    up_across = 0 if field_width < 1 else _along(field_width, label_width, gap_x)
    up_down = 0 if field_height < 1 else _along(field_height, label_height, gap_y)
    grids.append(
        {
            "across": up_across,
            "down": up_down,
            "total": up_across * up_down,
            "turned": False,
        }
    )
    if label["turn"]:
        side_across = (
            0 if field_width < 1 else _along(field_width, label_height, gap_x)
        )
        side_down = (
            0 if field_height < 1 else _along(field_height, label_width, gap_y)
        )
        grids.append(
            {
                "across": side_across,
                "down": side_down,
                "total": side_across * side_down,
                "turned": True,
            }
        )

    best = grids[0]
    for grid in grids:
        if grid["total"] > best["total"]:
            best = grid
    if best["total"] < 1:
        raise ValueError("not one label fits on this sheet")
    return best
