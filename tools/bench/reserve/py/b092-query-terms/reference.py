SIGN_KINDS = {"+": "must", "-": "not"}


def tokenize_query(text):
    if not isinstance(text, str) or text.strip() == "":
        raise ValueError("tokenize_query expects a non-empty query")
    pairs = []
    at = 0
    while at < len(text):
        if text[at] == " ":
            at += 1
            continue
        if text[at] == '"':
            close = text.find('"', at + 1)
            if close == -1:
                raise ValueError("a phrase is missing its closing quote")
            if close == at + 1:
                raise ValueError("a phrase may not be empty")
            pairs.append(["phrase", text[at + 1:close]])
            at = close + 1
            continue
        kind = "word"
        if text[at] in SIGN_KINDS:
            kind = SIGN_KINDS[text[at]]
            at += 1
        start = at
        while at < len(text) and text[at] != " ":
            at += 1
        if at == start:
            raise ValueError("a + or - needs a word after it")
        pairs.append([kind, text[start:at]])
    return pairs
