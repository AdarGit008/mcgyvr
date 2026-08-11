from solution import lap_best

assert lap_best([90, 0, 88]) == 88, "an uncompleted lap is ignored"
assert lap_best([90, 88]) == 88, "the quicker of two"
assert lap_best([0, 0]) == 0, "nothing was completed"
assert lap_best([]) == 0, "no laps at all"
assert lap_best([77]) == 77, "a single lap"
assert lap_best([0, 95, 0, 93]) == 93, "zeros scattered through"
print("ok")
