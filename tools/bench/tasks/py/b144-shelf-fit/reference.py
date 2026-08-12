def shelf_fit(widths, shelf):
    if not isinstance(widths, list):
        raise ValueError("shelf_fit expects a list of spine widths")
    if isinstance(shelf, bool) or not isinstance(shelf, int) or shelf < 0:
        raise ValueError("shelf must be a non-negative integer")
    for width in widths:
        if isinstance(width, bool) or not isinstance(width, int) or width < 1:
            raise ValueError("every spine width must be a positive integer")
    used = count = 0
    for width in widths:
        if used + width > shelf:
            break
        used += width
        count += 1
    return count
