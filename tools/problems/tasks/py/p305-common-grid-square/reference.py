import re

SQUARES = "ABCDEFGHJKLMNPQRSTUV"


def _read_box(reference: str) -> tuple[int, int, int]:
    if not isinstance(reference, str):
        raise ValueError("a reference is a string")
    if len(reference) < 2:
        raise ValueError("a reference opens with two capitals")
    column = SQUARES.find(reference[0])
    row = SQUARES.find(reference[1])
    if column < 0 or row < 0:
        raise ValueError("that capital is not on the projection")
    figures = reference[2:]
    if re.fullmatch(r"[0-9]*", figures) is None:
        raise ValueError("only decimal figures may trail the capitals")
    if len(figures) % 2 != 0 or len(figures) > 10:
        raise ValueError("the tally of figures is not readable")
    tally = len(figures) // 2
    side = 100000 // (10**tally)
    easting = column * 100000
    northing = row * 100000
    if tally > 0:
        easting += int(figures[:tally]) * side
        northing += int(figures[tally:]) * side
    return easting, northing, tally


def common_grid_square(references: list[str]) -> str:
    if not isinstance(references, list):
        raise ValueError("references must be a list")
    if not references:
        raise ValueError("there is nothing to enclose")
    boxes = [_read_box(reference) for reference in references]
    coarsest = min(box[2] for box in boxes)
    for tally in range(coarsest, -1, -1):
        side = 100000 // (10**tally)
        east = boxes[0][0] // side
        north = boxes[0][1] // side
        if any(box[0] // side != east or box[1] // side != north for box in boxes):
            continue
        origin_east = east * side
        origin_north = north * side
        letters = SQUARES[origin_east // 100000] + SQUARES[origin_north // 100000]
        if tally == 0:
            return letters
        east_figures = str((origin_east % 100000) // side).zfill(tally)
        north_figures = str((origin_north % 100000) // side).zfill(tally)
        return letters + east_figures + north_figures
    return ""
