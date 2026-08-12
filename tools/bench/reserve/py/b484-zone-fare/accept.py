from solution import zone_fare

assert zone_fare(["central", "market"]) == 200, "two stops sharing one zone"
assert zone_fare(["central", "harbour"]) == 400, "two zones touched"
assert zone_fare(["central", "harbour", "far"]) == 600, "three zones touched"
assert zone_fare(["central"]) == 200, "a single stop"
assert zone_fare(["far", "other"]) == 200, "unnamed stops share the outer zone"
assert zone_fare([]) == 0, "a journey calling nowhere"
print("ok")
