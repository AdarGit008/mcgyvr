TYPES = ["bit", "whole", "ratio", "word", "empty"]


def _read_type(value, what):
    if not isinstance(value, str) or value not in TYPES:
        raise ValueError("the " + what + " must name one of the five value types")
    return value


def _joined(left, right):
    if left == "empty" or right == "empty":
        raise ValueError("an empty cannot be joined")
    if left == "word" or right == "word":
        return "word"
    return "ratio" if left == "ratio" or right == "ratio" else "whole"


def _weighed(left, right):
    if left == "empty" or right == "empty":
        raise ValueError("an empty cannot be weighed")
    if left == "word" or right == "word":
        if left != right:
            raise ValueError("a word cannot be weighed against a number")
    return "bit"


def fold_coercion_chain(start: str, terms: list) -> list:
    running = _read_type(start, "starting type")
    if not isinstance(terms, list):
        raise ValueError("the terms must be a list")
    trail = []
    for term in terms:
        if not isinstance(term, dict):
            raise ValueError("every term must be a mapping")
        other = _read_type(term.get("type"), "term type")
        op = term.get("op")
        if op == "join":
            running = _joined(running, other)
        elif op == "weigh":
            running = _weighed(running, other)
        else:
            raise ValueError("a term's op must be join or weigh")
        trail.append(running)
    return trail
