import re

SHAPES = re.compile(
    r"(?<![A-Z])[A-Z]{2,4}-[0-9]{4,8}(?![0-9])"
    r"|(?<![a-z0-9])vk=[a-z0-9]{6,10}(?![a-z0-9])"
)


def mask_sensitive(note: str) -> dict:
    if not isinstance(note, str):
        raise ValueError("mask_sensitive expects a string")
    tally = {"badges": 0, "vaults": 0}

    def swap(found):
        seen = found.group(0)
        if seen.startswith("vk="):
            tally["vaults"] += 1
            return "[vault]"
        tally["badges"] += 1
        return re.sub(r"[0-9]", "#", seen)

    text = SHAPES.sub(swap, note)
    return {"text": text, "badges": tally["badges"], "vaults": tally["vaults"]}
