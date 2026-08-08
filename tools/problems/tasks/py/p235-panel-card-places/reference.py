def _whole(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _measure(panel, key, least):
    value = panel.get(key)
    if not _whole(value) or value < least:
        raise ValueError(key + " must be an integer of at least " + str(least))
    return value


def _fit_along(field, size, seam):
    if field < size:
        return 0
    return (field + seam) // (size + seam)


def place_cards(panel: dict, count: int, taken: list) -> list:
    if not isinstance(panel, dict):
        raise ValueError("the panel must be a record")
    width = _measure(panel, "width", 1)
    height = _measure(panel, "height", 1)
    bleed = _measure(panel, "bleed", 0)
    card_width = _measure(panel, "cardWidth", 1)
    card_height = _measure(panel, "cardHeight", 1)
    seam = _measure(panel, "seam", 0)
    if not _whole(count) or count < 0:
        raise ValueError("count must be a whole number of zero or more")
    if not isinstance(taken, list):
        raise ValueError("the spoken-for cells must be a list")

    columns = _fit_along(width - 2 * bleed, card_width, seam)
    rows = _fit_along(height - 2 * bleed, card_height, seam)
    cells = columns * rows
    if cells < 1:
        raise ValueError("this panel carries no cells")

    spoken = set()
    for cell in taken:
        if not _whole(cell) or cell < 1 or cell > cells:
            raise ValueError("cell " + str(cell) + " is not on this panel")
        spoken.add(cell)
    if cells - len(spoken) < count:
        raise ValueError("not enough free cells for " + str(count) + " cards")

    places = []
    for cell in range(1, cells + 1):
        if len(places) >= count:
            break
        if cell in spoken:
            continue
        column = (cell - 1) % columns
        row = (cell - 1) // columns
        places.append(
            [
                bleed + column * (card_width + seam),
                bleed + row * (card_height + seam),
            ]
        )
    return places
