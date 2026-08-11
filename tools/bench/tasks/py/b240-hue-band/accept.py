from solution import hue_band

assert hue_band(0) == "red", "the circle starts red"
assert hue_band(59) == "red", "just below the green edge"
assert hue_band(60) == "green", "green begins at its edge"
assert hue_band(179) == "green", "just below the blue edge"
assert hue_band(180) == "blue", "blue begins at its edge"
assert hue_band(300) == "red", "red returns at the far edge"
assert hue_band(400) == "red", "a reading past the circle wraps"
assert hue_band(-30) == "red", "a negative reading counts backwards"
print("ok")
