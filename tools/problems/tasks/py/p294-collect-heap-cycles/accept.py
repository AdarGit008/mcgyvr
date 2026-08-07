from solution import collect_heap_cycles


def cell(name, refs, finalizer):
    return {"id": name, "refs": refs, "finalizer": finalizer}


def rejects(heap, held):
    try:
        collect_heap_cycles(heap, held)
    except ValueError:
        return True
    return False


assert collect_heap_cycles([], []) == [], "no collections, no reports"
assert collect_heap_cycles([cell("a", [], False)], [["a"]]) == [
    {"finalized": [], "collected": []}
], "a held cell is painted and nothing is doomed"
assert collect_heap_cycles(
    [
        cell("a", ["b"], False),
        cell("b", [], False),
        cell("x", ["y"], False),
        cell("y", ["x"], False),
    ],
    [["a"]],
) == [{"finalized": [], "collected": ["x", "y"]}], "a ring nobody holds is swept whole"
assert collect_heap_cycles(
    [cell("a", ["f"], False), cell("f", [], True)], [["a"]]
) == [{"finalized": [], "collected": []}], (
    "a painted cell never has its finalizer run"
)
assert collect_heap_cycles(
    [cell("a", [], False), cell("m", ["n"], True), cell("n", [], True)],
    [["a", "m"], ["a"], ["a"]],
) == [
    {"finalized": [], "collected": []},
    {"finalized": ["m", "n"], "collected": []},
    {"finalized": [], "collected": ["m", "n"]},
], "the collection that runs a finalizer sweeps nothing it touched"
assert collect_heap_cycles(
    [cell("a", [], False), cell("m", ["n"], True), cell("n", [], True)],
    [["a", "m"], ["a", "n"], ["a"], ["a"]],
) == [
    {"finalized": [], "collected": []},
    {"finalized": ["m"], "collected": []},
    {"finalized": ["n"], "collected": ["m"]},
    {"finalized": [], "collected": ["n"]},
], "sparing n one round delays its own finalizer to the next"
assert collect_heap_cycles(
    [cell("r", [], False), cell("f", ["g"], True), cell("g", ["f"], True)],
    [["r"], ["r"]],
) == [
    {"finalized": ["f", "g"], "collected": []},
    {"finalized": [], "collected": ["f", "g"]},
], "two cells pointing at each other are finalized then swept"
assert collect_heap_cycles(
    [cell("a", [], False), cell("b", [], False), cell("c", [], False)],
    [["a", "a", "a"]],
) == [{"finalized": [], "collected": ["b", "c"]}], (
    "holding one id three times holds it once"
)

assert rejects("heap", []), "a heap is a list"
assert rejects([cell("a", [], False)], "roots"), "the held-id lists are a list"
assert rejects([{"refs": [], "finalizer": False}], []), "a cell needs an id"
assert rejects([cell("a", [], False), cell("a", [], True)], []), (
    "two cells may not share an id"
)
assert rejects([cell("a", ["ghost"], False)], []), "a ref must name a cell"
assert rejects([cell("a", [], "yes")], []), "the finalizer flag is a boolean"
assert rejects([cell("a", [], False)], [["b"]]), "a held id must name a cell"
assert rejects([cell("a", [], False), cell("z", [], False)], [["a"], ["z"]]), (
    "a swept cell can no longer be held"
)
print("ok")
