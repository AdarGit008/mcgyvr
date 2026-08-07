import re


def word_span_starts(passage, query):
    if not isinstance(passage, str) or not isinstance(query, str):
        raise ValueError("passage and query must be strings")

    def tokenize(text):
        return [
            (match.group(0).lower(), match.start())
            for match in re.finditer(r"[A-Za-z0-9]+", text)
        ]

    words = tokenize(passage)
    wanted = [word for word, _ in tokenize(query)]
    if not wanted:
        raise ValueError("query contains no words")
    hits = []
    for i in range(len(words) - len(wanted) + 1):
        if all(words[i + j][0] == wanted[j] for j in range(len(wanted))):
            hits.append(words[i][1])
    return hits
