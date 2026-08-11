from solution import step_back

assert step_back("FFB") == 2, "the peak is before the step back"
assert step_back("BBB") == 0, "never forward, never past zero"
assert step_back("FBFBFF") == 2, "the peak comes at the end"
assert step_back("") == 0, "no moves at all"
assert step_back("FxF") == 2, "an unknown letter is ignored"
assert step_back("BFF") == 1, "the walk climbs back out of a hole"
print("ok")
