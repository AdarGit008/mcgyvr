from solution import toggle_run

assert toggle_run(["on"]) is True, "switched on"
assert toggle_run(["on", "off"]) is False, "on then off"
assert toggle_run(["flip"]) is True, "flipped from off"
assert toggle_run(["flip", "flip"]) is False, "flipped back"
assert toggle_run([]) is False, "no instructions leaves it off"
assert toggle_run(["on", "x", "flip"]) is False, "an unknown step is ignored"
print("ok")
