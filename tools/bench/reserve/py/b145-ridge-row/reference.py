def ridge_row(heights, level):
    if not isinstance(heights, list):
        raise ValueError("ridge_row expects a list of elevations")
    if isinstance(level, bool) or not isinstance(level, int) or level < 1:
        raise ValueError("level must be a positive integer")
    row = ""
    for height in heights:
        if isinstance(height, bool) or not isinstance(height, int) or height < 0:
            raise ValueError("every elevation must be a non-negative integer")
        row += "#" if height >= level else "."
    return row
