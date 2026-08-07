from solution import reassemble_stream

assert (
    reassemble_stream(5, [[0, "he"], [2, "llo"]]) == "hello"
), "contiguous fragments in order"
assert (
    reassemble_stream(5, [[2, "llo"], [0, "he"]]) == "hello"
), "arrival order must not matter"
assert (
    reassemble_stream(5, [[0, "abc"], [2, "cde"]]) == "abcde"
), "agreeing overlap merges into one message"
assert (
    reassemble_stream(2, [[0, "hi"], [0, "hi"]]) == "hi"
), "an exact duplicate fragment is harmless"
assert (
    reassemble_stream(4, [[0, "abcd"], [1, "bc"]]) == "abcd"
), "a fragment wholly inside another is harmless"
assert reassemble_stream(0, []) == "", "an empty message needs no fragments"
assert (
    reassemble_stream(2, [[1, ""], [0, "ab"]]) == "ab"
), "zero-length fragments contribute nothing"


def rejects(total, fragments):
    try:
        reassemble_stream(total, fragments)
    except ValueError:
        return True
    return False


assert rejects(3, [[0, "ab"], [1, "xz"]]), "a disagreeing overlap is rejected"
assert rejects(3, [[0, "a"], [2, "c"]]), "an uncovered position is rejected"
assert rejects(3, [[1, "abc"]]), "a fragment running past the end is rejected"
assert rejects(2, [[-1, "ab"]]), "a negative offset is rejected"
print("ok")
