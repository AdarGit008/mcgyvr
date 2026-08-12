from solution import cell_name, grid_cells

assert cell_name(0, 0) == "A1", "the corner cell"
assert cell_name(2, 1) == "B3", "column letter then row number"
assert grid_cells(1, 3) == ["A1", "B1", "C1"], "one row across"
assert grid_cells(2, 2) == ["A1", "B1", "A2", "B2"], "row by row"
assert grid_cells(0, 5) == [], "no rows, no cells"
assert grid_cells(3, 1) == ["A1", "A2", "A3"], "one column down"
print("ok")
