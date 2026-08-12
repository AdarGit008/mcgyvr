def mark_list(scores: list, floor: int) -> list:
    """Scores written out, with a star against those that reach a floor."""
    out = []
    for score in scores:
        out.append(str(score) + "*" if score >= floor else str(score))
    return out
