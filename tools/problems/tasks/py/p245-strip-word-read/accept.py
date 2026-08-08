from solution import decode_bit_run

book = {"ash": "0", "birch": "10", "cedar": "110", "dogwood": "111"}

assert decode_bit_run(book, "") == [], "an empty strip puts nothing down"
assert decode_bit_run(book, "0") == ["ash"], "one short mark"
assert decode_bit_run(book, "010") == ["ash", "birch"], "a short mark then a longer one"
assert decode_bit_run(book, "110111") == ["cedar", "dogwood"], "two long marks"
assert decode_bit_run(book, "0011010") == [
    "ash",
    "ash",
    "cedar",
    "birch",
], "a strip that uses every width"
assert decode_bit_run({"solo": "1"}, "111") == [
    "solo",
    "solo",
    "solo",
], "a single-word codebook repeats"


def rejects(codebook, strip):
    try:
        decode_bit_run(codebook, strip)
    except ValueError:
        return True
    return False


assert rejects(42, "0"), "a non-mapping codebook is rejected"
assert rejects([], "0"), "a list codebook is rejected"
assert rejects({}, "0"), "a codebook naming no words is rejected"
assert rejects({"Ash": "0"}, "0"), "a capital in a key is rejected"
assert rejects({"ash": ""}, "0"), "an empty mark is rejected"
assert rejects({"ash": "02"}, "0"), "a mark holding 2 is rejected"
assert rejects({"ash": "0", "birch": "0"}, "0"), "two words on one mark are rejected"
assert rejects({"ash": "0", "birch": "01"}, "0"), "a mark opening another mark is rejected"
assert rejects(book, 101), "a non-string strip is rejected"
assert rejects(book, "02"), "a strip holding 2 is rejected"
assert rejects(book, "011"), "a strip with a ragged tail is rejected"
print("ok")
