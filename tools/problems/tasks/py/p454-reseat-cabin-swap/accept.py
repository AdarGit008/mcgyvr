from solution import reseat_cabin


def rider(name, seat, want):
    return {"name": name, "seat": seat, "want": want}


wide = {"rows": 3, "left": "AB", "right": "CD", "blocked": []}

assert reseat_cabin([rider("ann", "1A", "window"), rider("bob", "2C", "aisle")], wide) == {
    "seated": ["ann 1A kept", "bob 2C kept"],
    "bumped": [],
}, "a seat the swap leaves standing is kept"
assert reseat_cabin(
    [rider("ann", "4A", "window"), rider("bob", "4B", "any")], {"rows": 1, "left": "AB", "right": "CD", "blocked": []}
) == {"seated": ["ann 1A moved", "bob 1B moved"], "bumped": []}, (
    "rows the smaller cabin does not have send their holders forward"
)
assert reseat_cabin(
    [rider("ann", "1A", "window")], {"rows": 2, "left": "AB", "right": "CD", "blocked": ["1A"]}
) == {"seated": ["ann 1D moved"], "bumped": []}, (
    "a barred old seat is not kept and the search stays in the row it can"
)
assert reseat_cabin(
    [rider("ann", "1A", "any"), rider("bob", "1B", "any"), rider("cid", "1C", "any")],
    {"rows": 1, "left": "A", "right": "B", "blocked": []},
) == {"seated": ["ann 1A kept", "bob 1B kept"], "bumped": ["cid"]}, "a holder left with no seat at all is bumped"
assert reseat_cabin(
    [rider("zed", "2D", "window"), rider("ann", "1D", "window")],
    {"rows": 2, "left": "AB", "right": "CD", "blocked": ["1A", "1D", "2A", "2D"]},
) == {"seated": ["ann 1B shifted", "zed 1C shifted"], "bumped": []}, (
    "service runs by old seat, not by the order the holders were listed"
)
assert reseat_cabin(
    [rider("ann", "9A", "aisle")], {"rows": 1, "left": "AB", "right": "CD", "blocked": ["1B", "1C"]}
) == {"seated": ["ann 1A shifted"], "bumped": []}, (
    "a wish that cannot be met anywhere still gets a seat, marked shifted"
)
assert reseat_cabin(
    [rider("xan", "9Y", "window"), rider("yin", "9Z", "aisle")], {"rows": 1, "left": "A", "right": "BC", "blocked": []}
) == {"seated": ["xan 1A moved", "yin 1B moved"], "bumped": []}, (
    "a lone letter on one side counts as both a window and an aisle"
)
assert reseat_cabin([rider("ann", "1B", "window")], wide) == {"seated": ["ann 1B kept"], "bumped": []}, (
    "keeping the old seat outranks the wish"
)
assert reseat_cabin(
    [rider("ann", "9X", "window"), rider("bob", "9Y", "window")],
    {"rows": 3, "left": "AB", "right": "CD", "blocked": ["1A", "1D", "2A", "2D"]},
) == {"seated": ["ann 3A moved", "bob 3D moved"], "bumped": []}, (
    "the search spills into later rows when the early ones are barred"
)
assert reseat_cabin([], wide) == {"seated": [], "bumped": []}, "nobody aboard seats nobody"
assert reseat_cabin(
    [
        rider("ann", "1A", "window"),
        rider("bob", "1B", "aisle"),
        rider("cid", "1C", "aisle"),
        rider("dot", "1D", "window"),
        rider("eve", "2A", "any"),
    ],
    {"rows": 2, "left": "AB", "right": "CD", "blocked": ["1A", "2A"]},
) == {
    "seated": ["ann 1D moved", "bob 1B kept", "cid 1C kept", "dot 2D moved", "eve 2B moved"],
    "bumped": [],
}, "a displaced holder can take the seat a later holder was counting on"


def rejects(holders, cabin):
    try:
        reseat_cabin(holders, cabin)
    except ValueError:
        return True
    return False


assert rejects("no", wide), "holders that are not a list are refused"
assert rejects([], None), "a cabin that is not a record is refused"
assert rejects([], {"rows": 0, "left": "A", "right": "B", "blocked": []}), "nought rows is refused"
assert rejects([], {"rows": 1, "left": "a", "right": "B", "blocked": []}), "a small letter is refused"
assert rejects([], {"rows": 1, "left": "", "right": "B", "blocked": []}), "an empty side is refused"
assert rejects([], {"rows": 1, "left": "AB", "right": "BC", "blocked": []}), "a repeated letter is refused"
assert rejects([], {"rows": 1, "left": "A", "right": "B", "blocked": "1A"}), "blocked that is not a list is refused"
assert rejects([], {"rows": 1, "left": "A", "right": "B", "blocked": ["A1"]}), "a malformed barred seat is refused"
assert rejects([], {"rows": 1, "left": "A", "right": "B", "blocked": ["9A"]}), (
    "a barred seat outside the cabin is refused"
)
assert rejects([[1]], wide), "a holder that is not a record is refused"
assert rejects([rider("", "1A", "any")], wide), "an empty name is refused"
assert rejects([rider("a", "1A", "any"), rider("a", "1B", "any")], wide), "one name twice is refused"
assert rejects([rider("a", "0A", "any")], wide), "a row of nought in an old seat is refused"
assert rejects([rider("a", "1AB", "any")], wide), "two letters in an old seat are refused"
assert rejects([rider("a", "1A", "any"), rider("b", "1A", "any")], wide), "one old seat twice is refused"
assert rejects([rider("a", "1A", "middle")], wide), "an unknown wish is refused"
print("ok")
