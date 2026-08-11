def drop_blank(labels: list) -> list:
    """The labels that are not empty, in order."""
    return [label for label in labels if label != ""]
