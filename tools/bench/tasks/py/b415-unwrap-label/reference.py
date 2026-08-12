def unwrap_label(label: str) -> str:
    """A label with one surrounding pair of brackets removed."""
    if label.startswith("[") and label.endswith("]"):
        return label[1:-1]
    return label
