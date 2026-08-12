def center_banner(label: str, width: int, fill: str) -> str:
    if not isinstance(label, str) or "\n" in label:
        raise ValueError("label must be a single-line string")
    if isinstance(width, bool) or not isinstance(width, int) or width < 1:
        raise ValueError("width must be a positive integer")
    if len(label) > width:
        raise ValueError("label is wider than the board")
    if not isinstance(fill, str) or len(fill) != 1:
        raise ValueError("fill must be a single character")
    spare = width - len(label)
    left = spare // 2
    return fill * left + label + fill * (spare - left)
