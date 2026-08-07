def tag_item(name: str, tags: list[str] | None = None) -> list[str]:
    """Append name to tags, using a fresh list when none is given."""
    if tags is None:
        tags = []
    tags.append(name)
    return tags
