import re

SQUARES = "ABCDEFGHJKLMNPQRSTUV"


def decode_grid_reference(reference: str) -> list[int]:
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
    if len(figures) % 2 != 0:
        raise ValueError("the figures must split evenly between the two axes")
    if len(figures) > 10:
        raise ValueError("ten figures is the finest the projection carries")
    half = len(figures) // 2
    side = 100000 // (10**half)
    easting = column * 100000
    northing = row * 100000
    if half > 0:
        easting += int(figures[:half]) * side
        northing += int(figures[half:]) * side
    return [easting, northing]
