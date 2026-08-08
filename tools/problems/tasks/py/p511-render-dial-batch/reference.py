import re

BOOK = {
    "ashen": ("8", (2, 2, 3)),
    "brill": ("", (5, 3)),
    "cobal": ("44", (3, 3)),
}
RUN = re.compile(r"[0-9]+")


def render_dial_batch(rows) -> dict:
    """Dial strings for a batch of rows, and the tags of the rows that refuse."""
    if not isinstance(rows, list):
        raise ValueError("the rows must be a list")
    tags = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("a row must be a mapping")
        tag = row.get("tag")
        if not isinstance(tag, str) or not tag:
            raise ValueError("a row needs a non-empty tag")
        if tag in tags:
            raise ValueError("two rows carry the same tag")
        tags.append(tag)

    lines = []
    bad = []
    for index, row in enumerate(rows):
        exchange = row.get("exchange")
        if not isinstance(exchange, str) or exchange not in BOOK:
            bad.append(tags[index])
            continue
        line = row.get("line")
        if not isinstance(line, str) or RUN.fullmatch(line) is None:
            bad.append(tags[index])
            continue
        stem, cuts = BOOK[exchange]
        wanted = sum(cuts)
        if len(line) != wanted:
            bad.append(tags[index])
            continue
        parts = []
        cursor = 0
        for cut in cuts:
            parts.append(line[cursor : cursor + cut])
            cursor += cut
        body = "-".join(parts)
        lines.append({"tag": tags[index], "dial": body if stem == "" else "(" + stem + ")" + body})

    return {"lines": lines, "bad": bad}
