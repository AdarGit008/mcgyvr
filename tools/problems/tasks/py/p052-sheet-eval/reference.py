import re


def compute_sheet(cells: dict[str, str]) -> dict[str, int]:
    if not isinstance(cells, dict):
        raise ValueError("compute_sheet expects a dict of cells")
    values: dict[str, int] = {}
    visiting: set[str] = set()

    def evaluate(name: str) -> int:
        if name in values:
            return values[name]
        if name not in cells:
            raise ValueError(f"unknown cell {name}")
        if name in visiting:
            raise ValueError(f"reference cycle through {name}")
        visiting.add(name)
        raw = cells[name]
        if not isinstance(raw, str):
            raise ValueError("cell text must be a string")
        if raw.startswith("="):
            body = raw[1:]
            if body.strip() == "":
                raise ValueError("empty formula")
            result = 0
            for part in body.split("+"):
                term = part.strip()
                if re.fullmatch(r"-?\d+", term):
                    result += int(term)
                elif re.fullmatch(r"[A-Z]+\d+", term):
                    result += evaluate(term)
                else:
                    raise ValueError(f"malformed term {term!r}")
        elif re.fullmatch(r"-?\d+", raw.strip()):
            result = int(raw.strip())
        else:
            raise ValueError(f"malformed literal {raw!r}")
        visiting.discard(name)
        values[name] = result
        return result

    for name in cells:
        evaluate(name)
    return values
