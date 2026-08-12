ARITY = {"insert": 3, "delete": 3, "replace": 4}


def rollback_journal(lines, journal, count):
    if not isinstance(lines, list) or any(
        not isinstance(line, str) for line in lines
    ):
        raise ValueError("lines must be a list of strings")
    if not isinstance(journal, list):
        raise ValueError("journal must be a list")
    if (
        isinstance(count, bool)
        or not isinstance(count, int)
        or count < 0
        or count > len(journal)
    ):
        raise ValueError("count must be an integer from 0 to the journal length")
    doc = list(lines)
    for entry in reversed(journal[len(journal) - count :]):
        if (
            not isinstance(entry, list)
            or not entry
            or not isinstance(entry[0], str)
            or ARITY.get(entry[0]) != len(entry)
            or any(not isinstance(text, str) for text in entry[2:])
        ):
            raise ValueError("malformed journal entry")
        kind, index = entry[0], entry[1]
        limit = len(doc) if kind == "delete" else len(doc) - 1
        if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index <= limit:
            raise ValueError("entry index is outside the document")
        if kind == "insert":
            if doc[index] != entry[2]:
                raise ValueError("journal disagrees with the document")
            del doc[index]
        elif kind == "delete":
            doc.insert(index, entry[2])
        else:
            if doc[index] != entry[3]:
                raise ValueError("journal disagrees with the document")
            doc[index] = entry[2]
    return doc
