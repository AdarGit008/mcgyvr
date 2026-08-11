from solution import range_text, span_list

assert range_text(1, 3) == "1-3", "a run of several"
assert range_text(5, 5) == "5", "a run of one"
assert span_list([1, 2, 3]) == ["1-3"], "one unbroken run"
assert span_list([1, 2, 4]) == ["1-2", "4"], "a break makes two runs"
assert span_list([]) == [], "no numbers, no runs"
assert span_list([7]) == ["7"], "a single number"
assert span_list([1, 3, 5]) == ["1", "3", "5"], "nothing is consecutive"
print("ok")
