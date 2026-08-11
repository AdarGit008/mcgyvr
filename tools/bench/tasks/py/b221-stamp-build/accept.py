from solution import stamp_build

assert stamp_build(0, 0, 0) == 0, "the first release stamps as zero"
assert stamp_build(0, 0, 1) == 1, "a patch step is worth one"
assert stamp_build(0, 1, 0) == 1000, "a minor step is worth a thousand"
assert stamp_build(1, 0, 0) == 1000000, "a major step is worth a million"
assert stamp_build(2, 14, 3) == 2014003, "the three components pack together"
assert stamp_build(1, 9, 9) == 1009009, "a minor below ten keeps its field"
assert stamp_build(1, 10, 0) == 1010000, "the later release stamps higher"


def rejects(*args):
    try:
        stamp_build(*args)
    except ValueError:
        return True
    return False


assert rejects(1.5, 0, 0), "a fractional component is rejected"
assert rejects("1", 0, 0), "a string component is rejected"
assert rejects(True, 0, 0), "a boolean component is rejected"
assert rejects(-1, 0, 0), "a negative component is rejected"
assert rejects(0, 1000, 0), "a minor beyond its field is rejected"
print("ok")
