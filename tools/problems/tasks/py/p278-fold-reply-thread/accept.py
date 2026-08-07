from solution import fold_reply_thread

assert fold_reply_thread([["a", "", "hello"]]) == "a hello", "a lone opening message"
assert (
    fold_reply_thread([["a", "", "top"], ["b", "a", "re"], ["c", "", "other"]])
    == "a top\n> b re\nc other"
), "one answer, then a second conversation"
assert (
    fold_reply_thread(
        [["a", "", "one"], ["b", "a", "two"], ["c", "b", "three"], ["d", "a", "four"]]
    )
    == "a one\n> b two\n> > c three\n> d four"
), "an answer to an answer, then back out"
assert (
    fold_reply_thread([["b", "a", "child"], ["a", "", "root"]]) == "a root\n> b child"
), "an answer handed over before what it answers"
assert (
    fold_reply_thread(
        [
            ["a", "", "r1"],
            ["x", "", "r2"],
            ["b", "a", "c1"],
            ["y", "x", "c2"],
            ["c", "a", "c3"],
        ]
    )
    == "a r1\n> b c1\n> c c3\nx r2\n> y c2"
), "two conversations interleaved in the batch"
assert (
    fold_reply_thread(
        [["a", "", "1"], ["b", "a", "2"], ["c", "b", "3"], ["d", "c", "4"]]
    )
    == "a 1\n> b 2\n> > c 3\n> > > d 4"
), "a chain four deep"
assert (
    fold_reply_thread([["a", "", "same"], ["c", "a", "later"], ["b", "a", "earlier"]])
    == "a same\n> c later\n> b earlier"
), "answers keep the batch's own order, not the id's"


def rejects(messages):
    try:
        fold_reply_thread(messages)
    except ValueError:
        return True
    return False


assert rejects([]), "an empty batch is rejected"
assert rejects("a"), "a batch that is not a list is rejected"
assert rejects([["a", ""]]), "a message of two values is rejected"
assert rejects([["", "", "x"]]), "an empty id is rejected"
assert rejects([["a", "", "x"], ["a", "", "y"]]), "a repeated id is rejected"
assert rejects([["a", "z", "x"]]), "a parent naming nobody is rejected"
assert rejects([["a", "", "two\nlines"]]), "a text carrying a newline is rejected"
assert rejects([["a", "b", "x"], ["b", "a", "y"]]), "links in a circle are rejected"
assert rejects([["a", "", "x"], ["b", "b", "y"]]), "answering itself is rejected"
print("ok")
