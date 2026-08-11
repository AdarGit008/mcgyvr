from solution import lay_conveyor

floor = ["....", ".#..", "...."]

assert lay_conveyor(floor, 0, 0, 4) == ["====", ".#..", "...."], "a run spans a whole open row"
assert lay_conveyor(floor, 1, 2, 2) == ["....", ".#==", "...."], "a run laid east of a machine leaves the machine standing"
assert lay_conveyor(floor, 2, 1, 1) == ["....", ".#..", ".=.."], "a run of one cell marks one cell"
assert floor == ["....", ".#..", "...."], "the plan handed in is left as it was"


def rejects(*args):
    try:
        lay_conveyor(*args)
    except Exception:
        return True
    return False


assert rejects(floor, 0, 2, 3), "a run passing the last column is rejected"
assert rejects(floor, 1, 0, 3), "a run covering a machine is rejected"
print("ok")
