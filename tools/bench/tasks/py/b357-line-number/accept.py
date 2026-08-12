from solution import line_number

assert line_number("a\nb") == "1: a\n2: b", "two lines numbered"
assert line_number("only") == "1: only", "one line"
assert line_number("") == "", "nothing to number"
assert line_number("a\n\nc") == "1: a\n2: \n3: c", "an empty line still counts"
assert line_number("x\ny\nz") == "1: x\n2: y\n3: z", "three lines"
assert line_number("\n") == "1: \n2: ", "a lone break makes two lines"
print("ok")
