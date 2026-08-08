def count_strip_tilings(width: int) -> int:
    if isinstance(width, bool) or not isinstance(width, int) or width < 0:
        raise ValueError("width must be a non-negative whole number")
    two_back = 1
    one_back = 1
    if width == 0:
        return two_back
    for _ in range(2, width + 1):
        two_back, one_back = one_back, one_back + 2 * two_back
    return one_back
