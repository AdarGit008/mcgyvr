def _whole(value):
    return isinstance(value, int) and not isinstance(value, bool)


def plan_saddle_sheets(pages: int, binding: str) -> list:
    if not _whole(pages):
        raise ValueError("the page count is not a whole number")
    if pages < 1 or pages > 4000:
        raise ValueError("the page count falls outside one through four thousand")
    if binding not in ("left", "right"):
        raise ValueError("the binding is neither left nor right")

    padded = pages + ((4 - pages % 4) % 4)
    sheets = padded // 4

    def face(number):
        return "blank" if number > pages else str(number)

    lines = []
    for sheet in range(1, sheets + 1):
        front_left = padded + 2 - 2 * sheet
        front_right = 2 * sheet - 1
        back_left = 2 * sheet
        back_right = padded + 1 - 2 * sheet
        if binding == "left":
            front = (front_left, front_right)
            back = (back_left, back_right)
        else:
            front = (front_right, front_left)
            back = (back_right, back_left)
        lines.append(f"{sheet} front {face(front[0])} {face(front[1])}")
        lines.append(f"{sheet} back {face(back[0])} {face(back[1])}")
    return lines
