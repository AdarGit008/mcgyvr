from solution import render_dial_batch

assert render_dial_batch(
    [
        {"tag": "t1", "exchange": "ashen", "line": "1234567"},
        {"tag": "t2", "exchange": "brill", "line": "12345678"},
        {"tag": "t3", "exchange": "cobal", "line": "123456"},
        {"tag": "t4", "exchange": "ashen", "line": "12345678"},
        {"tag": "t5", "exchange": "brill", "line": "1234"},
        {"tag": "t6", "exchange": "cobal", "line": "12a456"},
        {"tag": "t7", "exchange": "delta", "line": "123456"},
        {"tag": "t8", "exchange": "cobal", "line": 123456},
    ]
) == {
    "lines": [
        {"tag": "t1", "dial": "(8)12-34-567"},
        {"tag": "t2", "dial": "12345-678"},
        {"tag": "t3", "dial": "(44)123-456"},
    ],
    "bad": ["t4", "t5", "t6", "t7", "t8"],
}, "the three sound rows render and the five faulty ones are minuted"
assert render_dial_batch([]) == {"lines": [], "bad": []}, "an empty batch renders nothing"
assert render_dial_batch([{"tag": "a", "exchange": "ashen", "line": "12345678"}]) == {
    "lines": [],
    "bad": ["a"],
}, "one digit too many is minuted, not quietly cut down"
assert render_dial_batch([{"tag": "a", "exchange": "brill", "line": "123456789"}]) == {
    "lines": [],
    "bad": ["a"],
}, "a stemless exchange refuses an over-long line just the same"
assert render_dial_batch([{"tag": "a", "exchange": "cobal", "line": "1234567890"}]) == {
    "lines": [],
    "bad": ["a"],
}, "four surplus digits are still surplus"
assert render_dial_batch([{"tag": "a", "exchange": "brill", "line": "00000000"}]) == {
    "lines": [{"tag": "a", "dial": "00000-000"}],
    "bad": [],
}, "a line of noughts of the right length renders"
assert render_dial_batch(
    [
        {"tag": "z", "exchange": "cobal", "line": "999999"},
        {"tag": "y", "exchange": "ashen", "line": "1111111"},
    ]
) == {
    "lines": [{"tag": "z", "dial": "(44)999-999"}, {"tag": "y", "dial": "(8)11-11-111"}],
    "bad": [],
}, "rows keep the order they arrived in"


def rejects(rows):
    try:
        render_dial_batch(rows)
    except ValueError:
        return True
    return False


assert rejects("rows"), "the rows must be a list"
assert rejects(["t1"]), "a row must be a mapping"
assert rejects([{"exchange": "ashen", "line": "1234567"}]), "a row needs a tag"
assert rejects([{"tag": "", "exchange": "ashen", "line": "1234567"}]), "an empty tag"
assert rejects(
    [
        {"tag": "same", "exchange": "ashen", "line": "1234567"},
        {"tag": "same", "exchange": "cobal", "line": "123456"},
    ]
), "two rows may not carry the same tag"
print("ok")
