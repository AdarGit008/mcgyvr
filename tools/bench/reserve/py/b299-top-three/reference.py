def top_three(scores: list) -> list:
    """The three highest scores, highest first."""
    return sorted(scores, reverse=True)[:3]
