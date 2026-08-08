from solution import normalize_part_code

assert (
    normalize_part_code("000000000") == "0000-0000-0"
), "the zero code verifies and gains its hyphens"
assert (
    normalize_part_code("aaaa aaaa k") == "AAAA-AAAA-K"
), "lowercase with spaces cleans, uppercases and verifies"
assert (
    normalize_part_code("1B2C3D4E8") == "1B2C-3D4E-8"
), "mixed digits and letters weigh out to 8"
assert (
    normalize_part_code("1b2c-3d4e-8") == "1B2C-3D4E-8"
), "hyphens anywhere are discarded before verification"
assert (
    normalize_part_code("0000-0000-0") == "0000-0000-0"
), "canonical input comes back canonical"
assert normalize_part_code("zzzzzzzzy") == "ZZZZ-ZZZZ-Y", "the top letter value folds to Y"


def rejects(value):
    try:
        normalize_part_code(value)
    except ValueError:
        return True
    return False


assert rejects("1B2C3D4E9"), "a wrong check character is rejected"
assert rejects("1B2C3D4E"), "eight cleaned characters are rejected"
assert rejects("1B2C3D4E88"), "ten cleaned characters are rejected"
assert rejects("1B2C_3D4E-8"), "an underscore is rejected"
assert rejects(42), "a number is rejected"
print("ok")
