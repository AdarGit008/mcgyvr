import re

LETTERS = re.compile(r"[a-z]+")


def _whole(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def fit_grid_words(slots: list, words: list) -> dict:
    if not isinstance(slots, list) or not slots:
        raise ValueError("the slots must be a non-empty list")
    ids = []
    spans = []
    sizes = []
    seen_id = set()
    held = set()
    for slot in slots:
        if not isinstance(slot, dict):
            raise ValueError("a slot must be a mapping")
        slot_id = slot.get("id")
        row = slot.get("row")
        col = slot.get("col")
        run = slot.get("run")
        size = slot.get("len")
        if not isinstance(slot_id, str) or not slot_id:
            raise ValueError("an id must be a non-empty string")
        if slot_id in seen_id:
            raise ValueError("two slots share an id")
        seen_id.add(slot_id)
        if not _whole(row) or row < 0 or not _whole(col) or col < 0:
            raise ValueError("a row and a column must be whole numbers of nought or more")
        if run not in ("across", "down"):
            raise ValueError("a run is either across or down")
        if not _whole(size) or size < 2:
            raise ValueError("a length must be a whole number of two or more")
        span = []
        for step in range(size):
            at = (row, col + step) if run == "across" else (row + step, col)
            if (run, at) in held:
                raise ValueError("two slots running the same way cover a square in common")
            held.add((run, at))
            span.append(at)
        ids.append(slot_id)
        spans.append(span)
        sizes.append(size)
    if not isinstance(words, list):
        raise ValueError("the words must be a list")
    seen_word = set()
    for word in words:
        if not isinstance(word, str) or LETTERS.fullmatch(word) is None:
            raise ValueError("a word must be lowercase letters a to z")
        if word in seen_word:
            raise ValueError("a word is offered twice")
        seen_word.add(word)

    grid = {}
    used = set()
    placed = []
    stuck = ""
    for at, slot_id in enumerate(ids):
        chosen = -1
        for which, word in enumerate(words):
            if which in used or len(word) != sizes[at]:
                continue
            agrees = True
            for step, letter in enumerate(word):
                held_letter = grid.get(spans[at][step])
                if held_letter is not None and held_letter != letter:
                    agrees = False
                    break
            if agrees:
                chosen = which
                break
        if chosen < 0:
            stuck = slot_id
            break
        used.add(chosen)
        word = words[chosen]
        for step, letter in enumerate(word):
            grid[spans[at][step]] = letter
        placed.append({"slot": slot_id, "word": word})
    return {"placed": placed, "stuck": stuck}
