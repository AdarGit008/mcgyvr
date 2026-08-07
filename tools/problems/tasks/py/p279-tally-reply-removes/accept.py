from solution import tally_reply_removes

assert tally_reply_removes([["a", ""]]) == [1], "one note starts and ends it"
assert tally_reply_removes([["a", ""], ["b", "a"], ["c", "a"]]) == [
    1,
    2,
], "two notes answer the same note"
assert tally_reply_removes([["a", ""], ["b", "a"], ["c", "b"], ["d", ""]]) == [
    2,
    1,
    1,
], "two discussions, one of them two removes deep"
assert tally_reply_removes([["a", ""], ["b", "a"], ["c", "b"], ["d", "c"]]) == [
    1,
    1,
    1,
    1,
], "a single file four removes long"
assert tally_reply_removes([["a", ""], ["b", ""], ["c", ""]]) == [
    3
], "nobody answers anybody"
assert tally_reply_removes([["b", "a"], ["a", ""]]) == [
    1,
    1,
], "the answer is listed before what it answers"
assert tally_reply_removes(
    [["r", ""], ["x", "r"], ["y", "r"], ["z", "r"], ["q", "x"]]
) == [1, 3, 1], "a wide remove and a narrow one below it"


def rejects(links):
    try:
        tally_reply_removes(links)
    except ValueError:
        return True
    return False


assert rejects([]), "an empty batch is rejected"
assert rejects("a"), "a batch that is not a list is rejected"
assert rejects([["a"]]), "a link of one value is rejected"
assert rejects([["", ""]]), "an empty id is rejected"
assert rejects([["a", ""], ["a", "a"]]), "an id used twice is rejected"
assert rejects([["a", "z"]]), "answering a note nobody sent is rejected"
assert rejects([["a", "b"], ["b", "a"]]), "answering in a circle is rejected"
assert rejects([["a", ""], ["b", "b"]]), "a note answering itself is rejected"
print("ok")
