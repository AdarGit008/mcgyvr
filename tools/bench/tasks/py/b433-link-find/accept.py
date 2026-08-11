from solution import link_find

assert link_find("a[one]b", "[", "]") == ["one"], "one piece between markers"
assert link_find("[a][b]", "[", "]") == ["a", "b"], "two pieces"
assert link_find("plain", "[", "]") == [], "no markers at all"
assert link_find("", "[", "]") == [], "an empty line"
assert link_find("[open", "[", "]") == [], "an opening never closed"
assert link_find("[]", "[", "]") == [""], "an empty piece still counts"
print("ok")
