from solution import row_key, index_rows

assert row_key("ann") == "A", "a lower-case name is raised"
assert row_key("Bob") == "B", "an upper-case name is already right"
assert index_rows(["ann", "amy", "bob"]) == {
    "A": ["ann", "amy"],
    "B": ["bob"],
}, "two groups in arrival order"
assert index_rows([]) == {}, "no names, no index"
assert index_rows(["Ann", "ann"]) == {
    "A": ["Ann", "ann"]
}, "case does not split a group"
assert index_rows(["zoe"]) == {"Z": ["zoe"]}, "one name, one group"
print("ok")
