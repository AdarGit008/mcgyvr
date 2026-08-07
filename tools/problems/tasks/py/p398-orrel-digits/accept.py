from solution import orrel_digits

assert orrel_digits(0) == "o", "nought is the lone mark"
assert orrel_digits(1) == "i", "one"
assert orrel_digits(2) == "y", "two"
assert orrel_digits(3) == "iyo", "three needs three places"
assert orrel_digits(5) == "iyy", "five"
assert orrel_digits(9) == "ioo", "nine sits on the third place alone"
assert orrel_digits(-1) == "iy", "minus one, with no minus sign"
assert orrel_digits(-3) == "io", "minus three sits on the second place"
assert orrel_digits(-9) == "iyoo", "minus nine"
assert orrel_digits(100) == "ioyoi", "a hundred"
assert orrel_digits(-100) == "iyiiiy", "minus a hundred"
assert orrel_digits(1000000) == "yiyooyiiiiooi", "the largest quantity allowed"


def rejects(value):
    try:
        orrel_digits(value)
    except ValueError:
        return True
    return False


assert rejects("4"), "text is not a number"
assert rejects(1.5), "a fraction is not whole"
assert rejects(None), "nothing at all is rejected"
assert rejects(1000001), "a quantity above the cap is rejected"
assert rejects(-1000001), "a quantity below the cap is rejected"
print("ok")
