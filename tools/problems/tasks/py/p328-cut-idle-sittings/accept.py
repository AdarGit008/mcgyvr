from solution import cut_idle_sittings

mixed = [
    {"who": "kim", "at": 100, "kind": "hit"},
    {"who": "kim", "at": 110, "kind": "hit"},
    {"who": "kim", "at": 200, "kind": "hit"},
    {"who": "ada", "at": 50, "kind": "hit"},
    {"who": "kim", "at": 105, "kind": "hit"},
    {"who": "ada", "at": 55, "kind": "reset"},
]

assert cut_idle_sittings([], 10, 10) == [], "no events make no sittings"
assert cut_idle_sittings(mixed, 30, 1000) == [
    {"who": "ada", "from": 50, "to": 50, "count": 1},
    {"who": "ada", "from": 55, "to": 55, "count": 1},
    {"who": "kim", "from": 100, "to": 110, "count": 3},
    {"who": "kim", "from": 200, "to": 200, "count": 1},
], "shuffled events are sorted per visitor and cut on the idle gap"
assert cut_idle_sittings(mixed, 100, 8) == [
    {"who": "ada", "from": 50, "to": 50, "count": 1},
    {"who": "ada", "from": 55, "to": 55, "count": 1},
    {"who": "kim", "from": 100, "to": 105, "count": 2},
    {"who": "kim", "from": 110, "to": 110, "count": 1},
    {"who": "kim", "from": 200, "to": 200, "count": 1},
], "a generous gap still yields to the cap on the span"

two = [
    {"who": "leo", "at": 0, "kind": "hit"},
    {"who": "leo", "at": 30, "kind": "hit"},
]
assert cut_idle_sittings(two, 30, 100) == [
    {"who": "leo", "from": 0, "to": 30, "count": 2}
], "a wait of exactly the gap keeps the sitting open"
assert cut_idle_sittings(two, 29, 100) == [
    {"who": "leo", "from": 0, "to": 0, "count": 1},
    {"who": "leo", "from": 30, "to": 30, "count": 1},
], "one minute past the gap cuts"
assert cut_idle_sittings(two, 100, 30) == [
    {"who": "leo", "from": 0, "to": 30, "count": 2}
], "a span of exactly the cap is allowed"
assert cut_idle_sittings(two, 100, 29) == [
    {"who": "leo", "from": 0, "to": 0, "count": 1},
    {"who": "leo", "from": 30, "to": 30, "count": 1},
], "one minute past the cap cuts"
assert cut_idle_sittings(two, 100, 0) == [
    {"who": "leo", "from": 0, "to": 0, "count": 1},
    {"who": "leo", "from": 30, "to": 30, "count": 1},
], "a cap of zero holds a sitting to one instant"
assert cut_idle_sittings(
    [{"who": "mo", "at": 5, "kind": "reset"}, {"who": "mo", "at": 5, "kind": "hit"}],
    10,
    10,
) == [
    {"who": "mo", "from": 5, "to": 5, "count": 2}
], "an opening reset is nothing special and the hit joins it"
assert cut_idle_sittings(
    [{"who": "mo", "at": 5, "kind": "hit"}, {"who": "mo", "at": 5, "kind": "reset"}],
    10,
    10,
) == [
    {"who": "mo", "from": 5, "to": 5, "count": 1},
    {"who": "mo", "from": 5, "to": 5, "count": 1},
], "events sharing a minute keep the order they were handed in"


def rejects(one, two_arg, three):
    try:
        cut_idle_sittings(one, two_arg, three)
    except ValueError:
        return True
    return False


assert rejects("events", 1, 1), "a non-list is rejected"
assert rejects([{"who": "kim", "at": 1}], 1, 1), "an event missing kind is rejected"
assert rejects(
    [{"who": "kim", "at": 1, "kind": "tap"}], 1, 1
), "an unknown kind is rejected"
assert rejects(
    [{"who": "kim", "at": 1.5, "kind": "hit"}], 1, 1
), "a fractional at is rejected"
assert rejects(
    [{"who": "", "at": 1, "kind": "hit"}], 1, 1
), "an empty visitor name is rejected"
assert rejects(mixed, -1, 10), "a negative gap is rejected"
assert rejects(mixed, 10, -1), "a negative cap is rejected"
assert rejects([["kim", 1, "hit"]], 1, 1), "an event that is a list is rejected"
print("ok")
