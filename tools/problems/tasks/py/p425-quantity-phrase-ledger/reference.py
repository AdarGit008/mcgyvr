import re

WORD = re.compile(r"[a-z]+")


def _read_lexicon(lexicon: dict[str, str]) -> dict[int, str]:
    if not isinstance(lexicon, dict):
        raise ValueError("the lexicon must be a mapping")
    if len(lexicon) < 2:
        raise ValueError("the lexicon must reach at least as far as 1")
    table: dict[int, str] = {}
    for figure in range(len(lexicon)):
        key = str(figure)
        if key not in lexicon:
            raise ValueError("the lexicon's figures must run on without a gap")
        word = lexicon[key]
        if not isinstance(word, str) or WORD.fullmatch(word) is None:
            raise ValueError("a lexicon word must be a run of lowercase letters")
        table[figure] = word
    return table


def phrase_quantity_ledger(entries: list[list], lexicon: dict[str, str]) -> str:
    table = _read_lexicon(lexicon)
    if not isinstance(entries, list):
        raise ValueError("the ledger must be a list of triples")

    order: list[str] = []
    totals: dict[str, int] = {}
    plural: dict[str, str] = {}
    for triple in entries:
        if not isinstance(triple, (list, tuple)) or len(triple) != 3:
            raise ValueError("a ledger line is a [tally, one, many] triple")
        tally, one, many = triple
        if (
            not isinstance(tally, int)
            or isinstance(tally, bool)
            or tally < 0
            or tally > 999
        ):
            raise ValueError("a tally must be a whole number from 0 through 999")
        for wording in (one, many):
            if not isinstance(wording, str) or WORD.fullmatch(wording) is None:
                raise ValueError("a wording must be a run of lowercase letters")
        if one not in totals:
            order.append(one)
            totals[one] = 0
            plural[one] = many
        elif plural[one] != many:
            raise ValueError(f"two ledger lines disagree on the many wording of {one}")
        totals[one] += tally

    parts: list[str] = []
    for key in order:
        total = totals[key]
        if total == 0:
            continue
        figure = table.get(total, str(total))
        wording = key if total == 1 else plural[key]
        parts.append(f"{figure} {wording}")

    if not parts:
        return "nothing at all"
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return f"{parts[0]} and {parts[1]}"
    return ", ".join(parts[:-1]) + ", and " + parts[-1]
