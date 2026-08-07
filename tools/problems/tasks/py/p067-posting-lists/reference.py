import re


def posting_lists(documents):
    if not isinstance(documents, list):
        raise ValueError("documents must be a list of strings")
    index = {}
    for at, text in enumerate(documents):
        if not isinstance(text, str):
            raise ValueError("each document must be a string")
        for match in re.finditer(r"[A-Za-z0-9]+", text):
            term = match.group(0).lower()
            if len(term) < 2 or term.isdigit():
                continue
            postings = index.setdefault(term, [])
            if not postings or postings[-1] != at:
                postings.append(at)
    return index
