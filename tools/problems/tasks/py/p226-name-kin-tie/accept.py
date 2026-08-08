from solution import name_kin_tie

LINKS = [
    {"child": "bo", "parent": "ada"},
    {"child": "cy", "parent": "ada"},
    {"child": "di", "parent": "bo"},
    {"child": "ed", "parent": "bo"},
    {"child": "fi", "parent": "cy"},
    {"child": "gus", "parent": "di"},
    {"child": "hal", "parent": "fi"},
    {"child": "ivy", "parent": "gus"},
    {"child": "jo", "parent": "hal"},
    {"child": "kim", "parent": "ivy"},
    {"child": "max", "parent": "di"},
    {"child": "max", "parent": "fi"},
    {"child": "quin", "parent": "gus"},
    {"child": "quin", "parent": "cy"},
    {"child": "kit", "parent": "lu"},
]


def ladder(depth):
    links = []
    for line in ("a", "b"):
        links.append({"child": line + "1", "parent": "root"})
        for at in range(2, depth + 1):
            links.append({"child": line + str(at), "parent": line + str(at - 1)})
    return links


def rejects(links, one, other):
    try:
        name_kin_tie(links, one, other)
    except ValueError:
        return True
    return False


assert name_kin_tie(LINKS, "bo", "bo") == "self", "a person set against themselves"
assert name_kin_tie(LINKS, "bo", "ada") == "parent", "one link straight up"
assert name_kin_tie(LINKS, "ada", "bo") == "child", "one link straight down"
assert name_kin_tie(LINKS, "gus", "ada") == "great-grandparent", "three links up"
assert name_kin_tie(LINKS, "ivy", "ada") == "great-great-grandparent", "four links up"
assert name_kin_tie(LINKS, "ada", "ivy") == "great-great-grandchild", "four links down"
assert name_kin_tie(LINKS, "di", "ed") == "sibling", "a shared parent"
assert name_kin_tie(LINKS, "di", "cy") == "aunt-or-uncle", "a parent's sibling"
assert name_kin_tie(LINKS, "cy", "di") == "niece-or-nephew", "the same tie read the other way"
assert name_kin_tie(LINKS, "gus", "cy") == "great-aunt-or-uncle", "a grandparent's sibling"
assert name_kin_tie(LINKS, "cy", "gus") == "great-niece-or-nephew", "and its mirror"
assert (
    name_kin_tie(LINKS, "ivy", "cy") == "great-great-aunt-or-uncle"
), "two greats deep on the collateral line"
assert name_kin_tie(LINKS, "di", "fi") == "first cousin", "two counts of two"
assert name_kin_tie(LINKS, "gus", "fi") == "first cousin once removed", "a generation apart"
assert name_kin_tie(LINKS, "fi", "gus") == "first cousin once removed", "removal does not take sides"
assert name_kin_tie(LINKS, "gus", "hal") == "second cousin", "two counts of three"
assert name_kin_tie(LINKS, "ivy", "jo") == "third cousin", "two counts of four"
assert (
    name_kin_tie(LINKS, "ivy", "hal") == "second cousin once removed"
), "degree from the smaller count"
assert name_kin_tie(LINKS, "ivy", "fi") == "first cousin twice removed", "two generations apart"
assert (
    name_kin_tie(LINKS, "kim", "fi") == "first cousin three times removed"
), "three generations apart"
assert name_kin_tie(LINKS, "bo", "kit") == "unrelated", "two people with no forebear in common"
assert name_kin_tie(LINKS, "max", "ed") == "aunt-or-uncle", "the nearer of two lines decides"
assert name_kin_tie(LINKS, "max", "hal") == "sibling", "one shared parent out of two is a sibling"
assert (
    name_kin_tie(LINKS, "quin", "bo") == "aunt-or-uncle"
), "the smallest greater count wins over the longer line"
assert name_kin_tie(LINKS, "quin", "di") == "grandparent", "and the same tie can read straight up"
assert name_kin_tie(ladder(11), "a11", "b11") == "tenth cousin", "the furthest degree there is"
assert (
    name_kin_tie(ladder(12), "a12", "b2") == "first cousin ten times removed"
), "the furthest removal there is"

assert rejects("links", "a", "b"), "links that are not a list are rejected"
assert rejects([["a", "b"]], "a", "b"), "a link that is not a mapping is rejected"
assert rejects([{"child": "", "parent": "a"}], "a", "a"), "an empty name is rejected"
assert rejects(
    [{"child": "a", "parent": "a"}], "a", "a"
), "someone made their own parent is rejected"
assert rejects(
    [{"child": "a", "parent": "b"}, {"child": "a", "parent": "b"}], "a", "b"
), "a link listed twice is rejected"
assert rejects(
    [
        {"child": "a", "parent": "b"},
        {"child": "a", "parent": "c"},
        {"child": "a", "parent": "d"},
    ],
    "a",
    "b",
), "a third parent is rejected"
assert rejects(
    [{"child": "a", "parent": "b"}, {"child": "b", "parent": "a"}], "a", "b"
), "links closing a loop are rejected"
assert rejects(LINKS, "zed", "bo"), "a second person nobody names is rejected"
assert rejects(LINKS, "bo", "zed"), "a third person nobody names is rejected"
assert rejects(LINKS, 5, "bo"), "a person who is not a string is rejected"
assert rejects(ladder(12), "a12", "b12"), "a degree past ten is rejected"
assert rejects(ladder(13), "a13", "b2"), "a removal past ten is rejected"

print("ok")
