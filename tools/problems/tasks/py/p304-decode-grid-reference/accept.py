from solution import decode_grid_reference


def rejects(reference):
    try:
        decode_grid_reference(reference)
    except ValueError:
        return True
    return False


assert decode_grid_reference("AA") == [0, 0], "AA is the origin square"
assert decode_grid_reference("BA") == [100000, 0], "the first capital walks east"
assert decode_grid_reference("AB") == [0, 100000], "the second capital walks north"
assert decode_grid_reference("VV") == [
    1900000,
    1900000,
], "V by V is the far north-east square"
assert decode_grid_reference("AA00") == [0, 0], "a pair of noughts stays in the corner"
assert decode_grid_reference("AA51") == [
    50000,
    10000,
], "one figure per axis cuts the square into tenths"
assert decode_grid_reference("KM1234") == [
    912000,
    1134000,
], "two figures per axis inside square KM"
assert decode_grid_reference("AA1234567890") == [
    12345,
    67890,
], "five figures per axis resolves to the metre"
assert decode_grid_reference("VV9999999999") == [
    1999999,
    1999999,
], "the finest box in the far corner"

assert rejects(42), "a number is not a reference"
assert rejects("A"), "one capital is too few"
assert rejects("IA"), "I was struck out of the alphabet"
assert rejects("AO"), "O was struck out of the alphabet"
assert rejects("aa"), "lower case is not a capital"
assert rejects("AA1"), "an odd count of figures cannot split"
assert rejects("AA123456789012"), "twelve figures overshoot the projection"
assert rejects("AA 12"), "a space is not a decimal figure"
print("ok")
