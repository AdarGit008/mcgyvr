import re


def hex_split(colour: str) -> list:
    if re.fullmatch(r"#[0-9a-fA-F]{6}", colour) is None:
        raise ValueError("not a six-digit colour: " + colour)
    return [colour[1:3], colour[3:5], colour[5:7]]


def hex_join(parts: list) -> str:
    return "#" + "".join(parts).lower()
