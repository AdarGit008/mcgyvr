from solution import mirror_step_rank

assert mirror_step_rank("0") == 0, "one mark, first position"
assert mirror_step_rank("1") == 1, "one mark, second position"

assert [mirror_step_rank(word) for word in ["00", "01", "11", "10"]] == [
    0,
    1,
    2,
    3,
], "the two-mark engraving runs straight up"

assert [
    mirror_step_rank(word)
    for word in ["000", "001", "011", "010", "110", "111", "101", "100"]
] == [0, 1, 2, 3, 4, 5, 6, 7], "the three-mark engraving runs straight up"

assert mirror_step_rank("0000") == 0, "four marks all clear"
assert mirror_step_rank("1000") == 15, "the far end of the four-mark dial"
assert mirror_step_rank("1100") == 8, "halfway round the four-mark dial"
assert mirror_step_rank("0101") == 6, "a four-mark word part way along"
assert mirror_step_rank("00000000") == 0, "eight clear marks still stand at nought"
assert (
    mirror_step_rank("11111111") == 170
), "eight marks all set, alternating in plain binary"
assert (
    mirror_step_rank("1" + "0" * 29) == 1073741823
), "the longest word allowed, at the far end of its dial"


def rejects(value):
    try:
        mirror_step_rank(value)
    except ValueError:
        return True
    return False


assert rejects(""), "an empty word is rejected"
assert rejects(101), "a number is not a word"
assert rejects("012"), "a stray mark is rejected"
assert rejects("10 1"), "a space is a stray mark"
assert rejects("0" * 31), "thirty-one marks is too long"
print("ok")
