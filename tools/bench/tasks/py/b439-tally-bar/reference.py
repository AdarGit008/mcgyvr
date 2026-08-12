def tally_bar(count: int, width: int) -> str:
    if count <= width:
        return "#" * count
    return "#" * (width - 1) + ">"
