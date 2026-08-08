from solution import fit_label_sheet


def sheet(width, height, margin_x, margin_y, gap_x, gap_y):
    return {
        "width": width,
        "height": height,
        "marginX": margin_x,
        "marginY": margin_y,
        "gapX": gap_x,
        "gapY": gap_y,
    }


def label(width, height, turn):
    return {"width": width, "height": height, "turn": turn}


def rejects(page, sticker):
    try:
        fit_label_sheet(page, sticker)
    except ValueError:
        return True
    return False


assert fit_label_sheet(
    sheet(210, 297, 10, 10, 0, 0), label(63, 38, False)
) == {"across": 3, "down": 7, "total": 21, "turned": False}, (
    "a plain gapless sheet"
)
assert fit_label_sheet(sheet(100, 100, 5, 5, 2, 2), label(20, 20, False)) == {
    "across": 4,
    "down": 4,
    "total": 16,
    "turned": False,
}, "gaps are demanded between neighbours only, never at the edges"
assert fit_label_sheet(sheet(100, 50, 0, 0, 0, 0), label(40, 20, True)) == {
    "across": 5,
    "down": 1,
    "total": 5,
    "turned": True,
}, "laying the label on its side wins when it yields more"
assert fit_label_sheet(sheet(40, 40, 0, 0, 0, 0), label(20, 10, True)) == {
    "across": 2,
    "down": 4,
    "total": 8,
    "turned": False,
}, "an equal count keeps the label upright"
assert fit_label_sheet(sheet(100, 50, 0, 0, 0, 0), label(40, 20, False)) == {
    "across": 2,
    "down": 2,
    "total": 4,
    "turned": False,
}, "a label forbidden to turn stays upright even when turning would pay"
assert fit_label_sheet(sheet(46, 20, 3, 0, 0, 0), label(40, 20, False)) == {
    "across": 1,
    "down": 1,
    "total": 1,
    "turned": False,
}, "a field exactly one label wide holds exactly one"
assert fit_label_sheet(sheet(64, 30, 2, 0, 5, 0), label(25, 30, False)) == {
    "across": 2,
    "down": 1,
    "total": 2,
    "turned": False,
}, "the last column pays no trailing gap"

assert rejects(sheet(30, 30, 5, 5, 0, 0), label(25, 25, True)), (
    "a label wider than the printable field is refused"
)
assert rejects(sheet(10, 10, 5, 1, 0, 0), label(2, 2, False)), (
    "margins that swallow the whole width are refused"
)
assert rejects(sheet(100, 100, 0, 0, 0, 0), label(0, 10, False)), (
    "a label measurement of zero is rejected"
)
assert rejects(sheet(100, 100, -1, 0, 0, 0), label(10, 10, False)), (
    "a negative margin is rejected"
)
assert rejects(sheet(100, 100, 0, 0, 1.5, 0), label(10, 10, False)), (
    "a fractional gap is rejected"
)
assert rejects(sheet(100, 100, 0, 0, 0, 0), {"width": 10, "height": 10}), (
    "a missing turn flag is rejected"
)
print("ok")
