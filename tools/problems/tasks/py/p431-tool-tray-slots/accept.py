from solution import fold_tool_tray


def touched(name):
    return ["touch", name]


def pinned(name):
    return ["pin", name]


def dropped(name):
    return ["drop", name]


def rejects(slots, actions):
    try:
        fold_tool_tray(slots, actions)
    except ValueError:
        return True
    return False


assert fold_tool_tray(2, []) == [], "no actions leaves the tray empty"
assert fold_tool_tray(2, [touched("a"), touched("b")]) == [
    "b",
    "a",
], "the tray reads newest touch first"
assert fold_tool_tray(2, [touched("a"), touched("b"), touched("a")]) == [
    "a",
    "b",
], "touching a held entry only refreshes it"
assert fold_tool_tray(2, [touched("a"), touched("b"), touched("c")]) == [
    "c",
    "b",
], "a full tray turns out its oldest touch"
assert fold_tool_tray(2, [touched("a"), pinned("a"), touched("b"), touched("c")]) == [
    "c",
    "*a",
], "a pinned entry is passed over when room is made"
assert fold_tool_tray(1, [touched("a"), pinned("a"), touched("b")]) == [
    "*a"
], "a tray of nothing but pins refuses the touch"
assert fold_tool_tray(
    3, [touched("a"), touched("b"), touched("a"), touched("c"), touched("d")]
) == ["d", "c", "a"], "a refreshed entry outlives one touched earlier"
assert fold_tool_tray(2, [touched("a"), pinned("a"), pinned("a"), touched("b")]) == [
    "b",
    "*a",
], "pinning twice changes nothing"
assert fold_tool_tray(
    2, [touched("a"), pinned("a"), dropped("a"), touched("b"), touched("c")]
) == ["c", "b"], "a drop turns out a pinned entry too"
assert fold_tool_tray(2, [pinned("z"), touched("a")]) == [
    "a"
], "pinning a name the tray lacks changes nothing"
assert fold_tool_tray(2, [touched("a"), dropped("z")]) == [
    "a"
], "dropping a name the tray lacks changes nothing"
assert fold_tool_tray(
    3,
    [touched("a"), touched("b"), pinned("b"), touched("c"), touched("d"), touched("e")],
) == ["e", "d", "*b"], "a longer replay keeps the pin through two turnings out"
assert fold_tool_tray(
    2,
    [touched("a"), pinned("a"), touched("b"), pinned("b"), dropped("a"), touched("c")],
) == ["c", "*b"], "dropping a pin frees the slot the refused touch wanted"

assert rejects(0, []), "a slots figure under 1 is refused"
assert rejects(2.5, []), "a fractional slots figure is refused"
assert rejects("2", []), "a slots figure that is not a number is refused"
assert rejects(2, [["touch"]]), "an action that is not a pair is refused"
assert rejects(2, [["poke", "a"]]), "an unknown verb is refused"
assert rejects(2, [["touch", ""]]), "an empty name is refused"
assert rejects(2, [["touch", "*a"]]), "a name carrying an asterisk is refused"
assert rejects(2, [["touch", 5]]), "a name that is not a string is refused"
print("ok")
