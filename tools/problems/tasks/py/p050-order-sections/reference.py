import re

_LABEL = re.compile(r"(?:0|[1-9]\d*)(?:\.(?:0|[1-9]\d*))*")


def order_sections(labels: list[str]) -> list[str]:
    if not isinstance(labels, list):
        raise ValueError("labels must be a list")
    seen = set()
    parsed = []
    for label in labels:
        if not isinstance(label, str) or _LABEL.fullmatch(label) is None:
            raise ValueError("malformed section label")
        if label in seen:
            raise ValueError("duplicate section label")
        seen.add(label)
        parsed.append((tuple(int(c) for c in label.split(".")), label))
    parsed.sort()
    return [label for _, label in parsed]
