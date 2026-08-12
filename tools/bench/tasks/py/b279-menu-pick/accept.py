from solution import menu_pick

soup = {"name": "soup", "price": 200}
pie = {"name": "pie", "price": 350}

assert menu_pick([soup, pie], 300) == ["soup"], "the dear one is dropped"
assert menu_pick([pie, soup], 400) == ["soup", "pie"], "cheapest leads"
assert menu_pick(
    [{"name": "tea", "price": 100}, {"name": "ale", "price": 100}], 100
) == ["ale", "tea"], "a tie is broken by name"
assert menu_pick([], 500) == [], "an empty menu"
assert menu_pick([pie], 100) == [], "nothing is affordable"
assert menu_pick(
    [
        {"name": "a", "price": 100},
        {"name": "b", "price": 100},
        {"name": "c", "price": 50},
    ],
    100,
) == ["c", "a", "b"], "price first, then name"
print("ok")
