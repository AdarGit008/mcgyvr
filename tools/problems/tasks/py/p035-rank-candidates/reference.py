def rank_candidates(candidates: list[str], query: str, limit: int) -> list[str]:
    if not isinstance(query, str) or not query:
        raise ValueError("query must be a non-empty string")
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
        raise ValueError("limit must be a positive integer")
    if not isinstance(candidates, list) or any(
        not isinstance(c, str) for c in candidates
    ):
        raise ValueError("candidates must be a list of strings")
    needle = query.lower()
    scored = []
    for pos, text in enumerate(candidates):
        hay = text.lower()
        if hay == needle:
            tier = 3
        elif hay.startswith(needle):
            tier = 2
        elif needle in hay:
            tier = 1
        else:
            continue
        scored.append((-tier, len(text), pos, text))
    scored.sort()
    return [text for _, _, _, text in scored[:limit]]
