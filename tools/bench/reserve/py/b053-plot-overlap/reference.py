"""Shared area of two rectangular garden plots on an integer grid."""


def plot_overlap(a, b):
    for plot in (a, b):
        if not isinstance(plot, list) or len(plot) != 4:
            raise ValueError("a plot is four integers: left, bottom, right, top")
        for edge in plot:
            if isinstance(edge, bool) or not isinstance(edge, int):
                raise ValueError("plot edges must be integers")
        if plot[0] >= plot[2] or plot[1] >= plot[3]:
            raise ValueError("a plot must have positive width and height")
    width = min(a[2], b[2]) - max(a[0], b[0])
    height = min(a[3], b[3]) - max(a[1], b[1])
    if width <= 0 or height <= 0:
        return 0
    return width * height
