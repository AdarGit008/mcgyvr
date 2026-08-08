from solution import replay_recent_panel


def opened(name):
    return ["open", name]


def pinned(name):
    return ["pin", name]


def unpinned(name):
    return ["unpin", name]


def forgotten(name):
    return ["forget", name]


def rejects(limit, events):
    try:
        replay_recent_panel(limit, events)
    except ValueError:
        return True
    return False


assert replay_recent_panel(3, []) == [], "no events leaves the panel empty"
assert replay_recent_panel(3, [opened("a"), opened("b"), opened("c")]) == [
    "c",
    "b",
    "a",
], "the recent region reads newest first"
assert replay_recent_panel(3, [opened("a"), opened("b"), opened("c"), opened("d")]) == [
    "d",
    "c",
    "b",
], "the oldest name is let go at the limit"
assert replay_recent_panel(3, [opened("a"), opened("b"), opened("c"), opened("a")]) == [
    "a",
    "c",
    "b",
], "opening a held name lifts it to the head"
assert replay_recent_panel(3, [opened("a"), opened("b"), pinned("a")]) == [
    "a",
    "b",
], "a pinned name leads the panel"
assert replay_recent_panel(
    2, [opened("a"), opened("b"), pinned("a"), opened("c"), opened("d")]
) == ["a", "d", "c"], "pinned names are held outside the limit"
assert replay_recent_panel(3, [pinned("a"), opened("b"), opened("a"), opened("c")]) == [
    "a",
    "c",
    "b",
], "opening a pinned name stirs nothing"
assert replay_recent_panel(2, [pinned("z")]) == ["z"], "a name never seen may be pinned"
assert replay_recent_panel(2, [pinned("a"), pinned("b"), pinned("c")]) == [
    "a",
    "b",
    "c",
], "the pinned region reads in pin order"
assert replay_recent_panel(2, [opened("x"), opened("y"), pinned("x"), unpinned("x")]) == [
    "x",
    "y",
], "an unpinned name returns at the head of the recent region"
assert replay_recent_panel(1, [opened("p"), opened("q"), pinned("p"), unpinned("p")]) == [
    "p"
], "an unpin trims the recent region the way an open does"
assert replay_recent_panel(3, [opened("a"), opened("b"), forgotten("a")]) == [
    "b"
], "forgetting drops a held name"
assert replay_recent_panel(3, [pinned("a"), forgotten("a")]) == [
    "a"
], "a pinned name cannot be forgotten"
assert replay_recent_panel(3, [opened("a"), forgotten("z")]) == [
    "a"
], "forgetting an unknown name stirs nothing"
assert replay_recent_panel(3, [opened("a"), unpinned("a")]) == [
    "a"
], "unpinning a name that is not pinned stirs nothing"
assert replay_recent_panel(3, [pinned("a"), pinned("b"), unpinned("a"), pinned("a")]) == [
    "b",
    "a",
], "a repinned name joins the tail of the pinned region"
assert replay_recent_panel(
    2,
    [
        opened("a"),
        pinned("a"),
        pinned("a"),
        opened("b"),
        opened("c"),
        opened("d"),
        forgotten("c"),
    ],
) == ["a", "d"], "a long replay over pins, drops and a forget"

assert rejects(0, []), "a limit under 1 is refused"
assert rejects(1.5, []), "a fractional limit is refused"
assert rejects("3", []), "a limit that is not a number is refused"
assert rejects(3, [["open"]]), "an event that is not a pair is refused"
assert rejects(3, [["close", "a"]]), "an unknown verb is refused"
assert rejects(3, [["open", ""]]), "an empty name is refused"
assert rejects(3, [["open", 7]]), "a name that is not a string is refused"
print("ok")
