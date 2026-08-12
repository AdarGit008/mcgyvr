from solution import shed_tail

assert shed_tail("filename..", ".") == "filename", "the piece comes off again and again"
assert shed_tail("report", ".") == "report", "the text never closes with the piece"
assert shed_tail("aXYXY", "XY") == "a", "a piece of more than one character"
assert shed_tail("keep.", ".") == "keep", "a single closing piece"
assert shed_tail("hold", "") == "hold", "a piece holding nothing"
assert shed_tail("", ".") == "", "a text holding nothing"
print("ok")
