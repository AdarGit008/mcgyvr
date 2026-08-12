from solution import route_stops, route_hops

assert route_stops("A>B>C") == ["A", "B", "C"], "three stops"
assert route_stops(" A > B ") == ["A", "B"], "spaces are trimmed"
assert route_stops("A") == ["A"], "a route of one stop"
assert route_stops("   ") == [], "a blank route has no stops"
assert route_hops("A>B>C") == 2, "one fewer than the stops"
assert route_hops("A") == 0, "a single stop is no journey"
assert route_hops("") == 0, "an empty route"
print("ok")
