import re

PLAN = {
    "kv": ("0", (3, 3, 3)),
    "mr": ("07", (4, 4)),
    "ts": ("+31", (2, 4, 4)),
    "wd": ("", (3, 4)),
}
RUN = re.compile(r"[0-9]+")


def format_subscriber_number(region: str, digits: str) -> str:
    if not isinstance(region, str) or region not in PLAN:
        raise ValueError("the region is not one this plan knows")
    if not isinstance(digits, str):
        raise ValueError("the digits must be a string")
    if RUN.fullmatch(digits) is None:
        raise ValueError("the digits must be nothing but digits")
    stem, blocks = PLAN[region]
    wanted = sum(blocks)
    if len(digits) != wanted:
        raise ValueError("the region wants exactly %d digits" % wanted)
    if digits[0] == "0":
        raise ValueError("a subscriber number never opens with a nought")
    parts = []
    cursor = 0
    for block in blocks:
        parts.append(digits[cursor : cursor + block])
        cursor += block
    body = " ".join(parts)
    return body if stem == "" else stem + " " + body
