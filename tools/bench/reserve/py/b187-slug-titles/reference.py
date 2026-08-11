def slug_titles(titles):
    if not isinstance(titles, list):
        raise ValueError("slug_titles expects a list of titles")
    seen = {}
    slugs = []
    for title in titles:
        if not isinstance(title, str):
            raise ValueError("every title must be a string")
        base = ""
        for ch in title.lower():
            if ch.isascii() and ch.isalnum():
                base += ch
            elif base and not base.endswith("-"):
                base += "-"
        base = base.rstrip("-")
        if not base:
            raise ValueError("a title must hold a letter or a digit")
        claim = seen.get(base, 0) + 1
        seen[base] = claim
        slugs.append(base if claim == 1 else base + "-" + str(claim))
    return slugs
