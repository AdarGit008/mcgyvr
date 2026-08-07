from solution import lay_pallet_row


def box(name, alen, blen, mass, tender):
    return {"name": name, "alen": alen, "blen": blen, "mass": mass, "tender": tender}


assert lay_pallet_row(
    [box("a", 10, 4, 5, False), box("b", 8, 4, 5, False)], {"run": 30, "span": 6, "load": 100}
) == {"laid": ["a flat", "b flat"], "skipped": [], "run": 12, "mass": 10}, (
    "two boxes that fit as they come are laid as they come"
)
assert lay_pallet_row([box("wide", 9, 3, 5, False)], {"run": 5, "span": 10, "load": 100}) == {
    "laid": ["wide turned"],
    "skipped": [],
    "run": 2,
    "mass": 5,
}, "a quarter turn saves a box too long for the run"
assert lay_pallet_row([box("wide", 9, 3, 5, True)], {"run": 5, "span": 10, "load": 100}) == {
    "laid": [],
    "skipped": ["wide"],
    "run": 5,
    "mass": 0,
}, "a tender box is never turned, so it is passed over"
assert lay_pallet_row([box("sq", 4, 3, 5, False)], {"run": 10, "span": 10, "load": 100}) == {
    "laid": ["sq flat"],
    "skipped": [],
    "run": 6,
    "mass": 5,
}, "when both lies work the box goes down as it comes"
assert lay_pallet_row(
    [box("a", 12, 5, 10, False), box("b", 9, 3, 10, False), box("c", 20, 20, 10, False), box("d", 4, 4, 10, False)],
    {"run": 20, "span": 8, "load": 100},
) == {"laid": ["a flat", "d flat"], "skipped": ["b", "c"], "run": 4, "mass": 20}, (
    "boxes behind a passed-over one are still tried"
)
assert lay_pallet_row(
    [box("a", 4, 4, 60, False), box("b", 4, 4, 60, False), box("c", 4, 4, 10, False)],
    {"run": 40, "span": 8, "load": 100},
) == {"laid": ["a flat", "c flat"], "skipped": ["b"], "run": 32, "mass": 70}, (
    "the load rating passes over a heavy box and a lighter one still goes down"
)
assert lay_pallet_row([box("a", 2, 9, 1, False)], {"run": 40, "span": 8, "load": 100}) == {
    "laid": ["a turned"],
    "skipped": [],
    "run": 31,
    "mass": 1,
}, "a box too broad across the span is turned to run down the deck"
assert lay_pallet_row([], {"run": 5, "span": 5, "load": 5}) == {
    "laid": [],
    "skipped": [],
    "run": 5,
    "mass": 0,
}, "no boxes leaves the run untouched"
assert lay_pallet_row([box("a", 5, 5, 5, False)], {"run": 5, "span": 5, "load": 5}) == {
    "laid": ["a flat"],
    "skipped": [],
    "run": 0,
    "mass": 5,
}, "a box sitting exactly on every rating goes down"
assert lay_pallet_row([box("a", 1, 1, 1, False)], {"run": 5, "span": 5, "load": 0}) == {
    "laid": [],
    "skipped": ["a"],
    "run": 5,
    "mass": 0,
}, "a load rating of nought takes nothing at all"
assert lay_pallet_row([box("p", 7, 2, 1, False), box("q", 2, 2, 1, False)], {"run": 4, "span": 8, "load": 10}) == {
    "laid": ["p turned", "q flat"],
    "skipped": [],
    "run": 0,
    "mass": 2,
}, "a turned box eats only its short side of the run"


def rejects(boxes, deck):
    try:
        lay_pallet_row(boxes, deck)
    except ValueError:
        return True
    return False


tiny = {"run": 1, "span": 1, "load": 1}
assert rejects("no", tiny), "boxes that are not a list are refused"
assert rejects([], 7), "a deck that is not a record is refused"
assert rejects([], {"run": 0, "span": 1, "load": 1}), "a run of nought is refused"
assert rejects([], {"run": 1, "span": 1.5, "load": 1}), "a fractional span is refused"
assert rejects([], {"run": 1, "span": 1, "load": -1}), "a negative load rating is refused"
assert rejects([], {"run": 1, "span": 1}), "a missing load rating is refused"
assert rejects([[1, 2]], tiny), "a box that is not a record is refused"
assert rejects([box("", 1, 1, 1, False)], tiny), "an empty name is refused"
assert rejects(
    [box("a", 1, 1, 1, False), box("a", 2, 2, 2, False)], {"run": 9, "span": 9, "load": 9}
), "two boxes answering to one name are refused"
assert rejects([box("a", 0, 1, 1, False)], tiny), "a side of nought is refused"
assert rejects([box("a", 1, 1, 1.5, False)], tiny), "a fractional mass is refused"
assert rejects([box("a", 1, 1, 1, 0)], tiny), "a tender flag that is not a boolean is refused"
print("ok")
