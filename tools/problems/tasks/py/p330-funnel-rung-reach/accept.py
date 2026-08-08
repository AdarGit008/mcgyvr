from solution import funnel_rung_reach

ladder = ["view", "cart", "pay"]
marks = [
    ["u1", "view", 10],
    ["u1", "cart", 20],
    ["u1", "pay", 30],
    ["u2", "view", 10],
    ["u2", "pay", 20],
    ["u3", "cart", 5],
    ["u3", "view", 10],
    ["u3", "cart", 20],
    ["u4", "view", 10],
    ["u4", "cart", 10],
    ["u5", "browse", 1],
]

assert funnel_rung_reach(marks, ladder, 100) == [
    ["view", 4],
    ["cart", 2],
    ["pay", 1],
], "a cart before the view does not count and an equal at does not either"
assert funnel_rung_reach(marks, ladder, 15) == [
    ["view", 4],
    ["cart", 2],
    ["pay", 0],
], "the window cuts the last rung off"
assert funnel_rung_reach(marks, ladder, 0) == [
    ["view", 4],
    ["cart", 0],
    ["pay", 0],
], "a window of nothing leaves only the first rung reachable"
assert funnel_rung_reach([], ladder, 100) == [
    ["view", 0],
    ["cart", 0],
    ["pay", 0],
], "no marks credit nobody"
assert funnel_rung_reach(marks, ["view"], 0) == [
    ["view", 4]
], "a ladder of one rung counts everyone who was seen"
assert funnel_rung_reach(
    [["u5", "a", 0], ["u5", "b", 100], ["u5", "a", 99]], ["a", "b"], 5
) == [
    ["a", 1],
    ["b", 1],
], "a later start rescues an actor whose first attempt ran out of window"
assert funnel_rung_reach([["u5", "a", 0], ["u5", "b", 100]], ["a", "b"], 5) == [
    ["a", 1],
    ["b", 0],
], "with no later start the window bites"
assert funnel_rung_reach([["u6", "elsewhere", 4]], ["a", "b"], 100) == [
    ["a", 0],
    ["b", 0],
], "a mark outside the ladder is ignored outright"


def rejects(one, two, three):
    try:
        funnel_rung_reach(one, two, three)
    except ValueError:
        return True
    return False


assert rejects(marks, [], 10), "an empty ladder is rejected"
assert rejects(marks, ["view", "view"], 10), "a ladder naming one step twice is rejected"
assert rejects(marks, ["view", ""], 10), "an empty ladder step is rejected"
assert rejects("marks", ladder, 10), "marks that are not a list are rejected"
assert rejects([["u1", "view"]], ladder, 10), "a mark of two items is rejected"
assert rejects([["u1", "view", 1.5]], ladder, 10), "a fractional at is rejected"
assert rejects([["", "view", 1]], ladder, 10), "an empty actor name is rejected"
assert rejects(marks, ladder, -1), "a negative window is rejected"
print("ok")
