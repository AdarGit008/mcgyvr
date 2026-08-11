from solution import tally_by_unit

mass = {"t": 1000000, "kg": 1000, "g": 1}

assert tally_by_unit([("flour", 3, "kg")], mass) == {"flour": (3, "kg")}, "a lone entry keeps its own unit"
assert tally_by_unit([("flour", 1, "kg"), ("flour", 500, "g")], mass) == {"flour": (1500, "g")}, "a total no larger unit divides drops to the base"
assert tally_by_unit([("sand", 2000, "kg")], mass) == {"sand": (2, "t")}, "an exactly divisible total climbs to the largest unit"
assert tally_by_unit([("salt", 0, "g")], mass) == {"salt": (0, "t")}, "a total of zero is reported in the largest unit"
assert tally_by_unit([("oats", 2, "kg"), ("rice", 250, "g")], mass) == {"oats": (2, "kg"), "rice": (250, "g")}, "items are totalled apart"
assert tally_by_unit([], mass) == {}, "no entries give an empty mapping"
assert tally_by_unit([("nail", 3, "box"), ("nail", 6, "single")], {"box": 12, "single": 1}) == {"nail": (42, "single")}, "the table given drives the report"
print("ok")
