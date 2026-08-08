from solution import changed_cells

assert changed_cells({"A1": "1", "B1": "=A1", "C1": "=B1"}, "A1", "2") == [
    "A1",
    "B1",
    "C1",
], "a change must ripple through intermediate formulas"
assert changed_cells(
    {"A1": "1", "B1": "=A1", "C1": "=A1", "D1": "=B1+C1"}, "A1", "3"
) == ["A1", "B1", "C1", "D1"], "diamond dependencies report each cell once"
assert (
    changed_cells({"A1": "1", "B1": "=A1"}, "A1", "1") == []
), "an identical rewrite changes nothing"
assert (
    changed_cells({"A1": "1", "B1": "=A1"}, "A1", "+1") == []
), "an equivalent respelling of the same integer changes nothing"
assert changed_cells({"A1": "1", "B1": "2", "C1": "=B1"}, "A1", "9") == [
    "A1"
], "cells not depending on the edit stay out of the report"
assert changed_cells({"A1": "2", "B1": "=A1", "C1": "=B1+A1"}, "B1", "7") == [
    "B1",
    "C1",
], "editing a formula cell to a literal reports its dependents"
assert changed_cells({"A1": "1", "B1": "5", "C1": "=B1"}, "B1", "=A1") == [
    "B1",
    "C1",
], "the replacement text may itself be a formula"


def rejects(sheet, name, replacement):
    try:
        changed_cells(sheet, name, replacement)
    except ValueError:
        return True
    return False


assert rejects({"A1": "1"}, "Q9", "2"), "editing an absent cell is rejected"
print("ok")
