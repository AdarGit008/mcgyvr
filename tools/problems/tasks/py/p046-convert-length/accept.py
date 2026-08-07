from solution import convert_length

assert convert_length("1km 250m", "m") == 1250, "kilometres fold into metres"
assert convert_length("2cm 5mm", "mm") == 25, "centimetres fold into millimetres"
assert convert_length("5mm 2cm", "mm") == 25, "part order is irrelevant"
assert convert_length("3m 20m", "m") == 23, "a symbol may recur"
assert convert_length("3000mm", "m") == 3, "an even conversion upward succeeds"
assert convert_length("42km", "km") == 42, "identity conversion"
assert convert_length("0mm", "km") == 0, "zero converts into anything"
assert convert_length("1km", "mm") == 1000000, "a kilometre is a million millimetres"


def rejects(quantity, goal):
    try:
        convert_length(quantity, goal)
    except ValueError:
        return True
    return False


assert rejects("1500mm", "m"), "an uneven conversion refuses"
assert rejects("5mm", "cm"), "half a centimetre refuses"
assert rejects("3in", "mm"), "a foreign symbol refuses"
assert rejects("3 mm", "mm"), "a detached number refuses"
assert rejects("2m", "yd"), "an unknown target refuses"
assert rejects("", "m"), "the empty quantity refuses"
print("ok")
