"""Fill-down for a rectangular grid of strings: blanks inherit from above."""


def blank_cells(rows):
    return sum(1 for row in rows for cell in row if cell == "")


def fill_down(rows):
    width = len(rows[0]) if rows else 0
    carry = {}
    filled = []
    for row in rows:
        if len(row) != width:
            raise ValueError("rows must all share one width")
        out = []
        for i, cell in enumerate(row):
            if cell != "":
                carry[i] = cell
            elif i not in carry:
                raise ValueError("a blank cell needs a filled cell above it")
            out.append(carry[i])
        filled.append(out)
    return filled
