from solution import band_picks_by_share

stock = [
    {"code": "K7", "picks": 600},
    {"code": "B2", "picks": 250},
    {"code": "A9", "picks": 80},
    {"code": "M1", "picks": 40},
    {"code": "Z3", "picks": 20},
    {"code": "Q5", "picks": 10},
]
aisle = [
    {"code": "R1", "capacity": 1},
    {"code": "R2", "capacity": 2},
    {"code": "R3", "capacity": 2},
    {"code": "R4", "capacity": 4},
]

assert band_picks_by_share(stock, [70, 90], aisle) == [
    {"code": "K7", "band": "A", "row": "R1", "slot": 1},
    {"code": "B2", "band": "A", "row": "R2", "slot": 1},
    {"code": "A9", "band": "B", "row": "R3", "slot": 1},
    {"code": "M1", "band": "C", "row": "R4", "slot": 1},
    {"code": "Z3", "band": "C", "row": "R4", "slot": 2},
    {"code": "Q5", "band": "C", "row": "R4", "slot": 3},
], "three bands, each starting on its own row"

assert band_picks_by_share(stock, [55, 90], aisle) == [
    {"code": "K7", "band": "A", "row": "R1", "slot": 1},
    {"code": "B2", "band": "B", "row": "R2", "slot": 1},
    {"code": "A9", "band": "B", "row": "R2", "slot": 2},
    {"code": "M1", "band": "C", "row": "R3", "slot": 1},
    {"code": "Z3", "band": "C", "row": "R3", "slot": 2},
    {"code": "Q5", "band": "C", "row": "R4", "slot": 1},
], "a tighter first cut moves the split, and a full row opens the next"

assert band_picks_by_share(
    [{"code": "D", "picks": 50}, {"code": "C", "picks": 50}, {"code": "A", "picks": 100}],
    [50, 80],
    [{"code": "F1", "capacity": 1}, {"code": "F2", "capacity": 3}],
) == [
    {"code": "A", "band": "A", "row": "F1", "slot": 1},
    {"code": "C", "band": "B", "row": "F2", "slot": 1},
    {"code": "D", "band": "B", "row": "F2", "slot": 2},
], "equal picks rank by code, and an empty band takes no row"

assert band_picks_by_share(
    [{"code": "X", "picks": 70}, {"code": "Y", "picks": 20}, {"code": "Z", "picks": 10}],
    [70, 90],
    [{"code": "W", "capacity": 1}, {"code": "V", "capacity": 1}, {"code": "U", "capacity": 1}],
) == [
    {"code": "X", "band": "A", "row": "W", "slot": 1},
    {"code": "Y", "band": "B", "row": "V", "slot": 1},
    {"code": "Z", "band": "C", "row": "U", "slot": 1},
], "landing exactly on a cut sends the line to the next band"

assert band_picks_by_share(
    [{"code": "S", "picks": 5}, {"code": "T", "picks": 0}],
    [40, 90],
    [{"code": "G1", "capacity": 5}, {"code": "G2", "capacity": 5}],
) == [
    {"code": "S", "band": "A", "row": "G1", "slot": 1},
    {"code": "T", "band": "C", "row": "G2", "slot": 1},
], "a line never pulled falls to the last band"


def rejects(lines, cuts, rows):
    try:
        band_picks_by_share(lines, cuts, rows)
    except ValueError:
        return True
    return False


assert rejects("x", [70, 90], aisle), "lines not a list"
assert rejects([], [70, 90], aisle), "no lines at all"
assert rejects([7], [70, 90], aisle), "a line that is not a record"
assert rejects([{"code": "", "picks": 3}], [70, 90], aisle), "an empty code"
assert rejects(
    [{"code": "A", "picks": 3}, {"code": "A", "picks": 4}], [70, 90], aisle
), "one code twice"
assert rejects([{"code": "A", "picks": -1}], [70, 90], aisle), "negative picks"
assert rejects([{"code": "A", "picks": 0}], [70, 90], aisle), "nothing pulled at all"
assert rejects(stock, [70], aisle), "only one cut"
assert rejects(stock, [0, 90], aisle), "a cut below one"
assert rejects(stock, [70, 100], aisle), "a cut above ninety-nine"
assert rejects(stock, [90, 70], aisle), "cuts the wrong way round"
assert rejects(stock, [70, 90], []), "no rows at all"
assert rejects(stock, [70, 90], [{"code": "R1"}]), "no capacity"
assert rejects(stock, [70, 90], [{"code": "R1", "capacity": 0}]), "a capacity of nothing"
assert rejects(
    stock, [70, 90], [{"code": "R1", "capacity": 2}, {"code": "R1", "capacity": 2}]
), "one row code twice"
assert rejects(stock, [70, 90], [{"code": "R1", "capacity": 2}]), "the rows run out"
print("ok")
