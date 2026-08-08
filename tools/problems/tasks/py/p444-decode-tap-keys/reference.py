KEYS = {
    "0": " ",
    "2": "ABC",
    "3": "DEF",
    "4": "GHI",
    "5": "JKL",
    "6": "MNO",
    "7": "PQRS",
    "8": "TUV",
    "9": "WXYZ",
}


def decode_tap_keys(taps: str) -> str:
    if not isinstance(taps, str):
        raise ValueError("the tap sequence must be a string")
    if taps == "":
        raise ValueError("the tap sequence is empty")
    if taps.startswith("-") or taps.endswith("-"):
        raise ValueError("a hyphen may not sit at either end")
    if "--" in taps:
        raise ValueError("two hyphens in a row")

    pieces = []
    key = ""
    taken = 0

    def settle():
        nonlocal key, taken
        if taken > 0:
            pieces.append(KEYS[key][taken - 1])
        key = ""
        taken = 0

    for mark in taps:
        if mark == "-":
            settle()
            continue
        if mark not in KEYS:
            raise ValueError(f"key {mark} carries no letters")
        if mark != key:
            settle()
            key = mark
        taken += 1
        if taken > len(KEYS[key]):
            raise ValueError(f"key {key} does not carry {taken} letters")
    settle()
    return "".join(pieces)
