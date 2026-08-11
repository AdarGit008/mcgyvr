from solution import reachable_modes

panel = {
    "idle": {"power": "warming", "diag": "service"},
    "warming": {"ready": "printing"},
    "printing": {"done": "idle", "jam": "fault"},
    "fault": {"clear": "idle"},
    "service": {"done": "idle", "eject": "sleep"},
    "offline": {"power": "idle"},
    "locked": {},
}

assert reachable_modes(panel, "idle") == ["fault", "idle", "printing", "service", "sleep", "warming"], "signals chain onward and a resting mode counts"
assert reachable_modes(panel, "offline") == ["fault", "idle", "offline", "printing", "service", "sleep", "warming"], "an entry mode reaches the whole panel"
assert reachable_modes(panel, "locked") == ["locked"], "a mode answering no signal reaches only itself"
assert reachable_modes({"armed": {"fire": "armed"}}, "armed") == ["armed"], "a signal leading back to its own mode settles"


def rejects(table, start):
    try:
        reachable_modes(table, start)
    except ValueError:
        return True
    return False


assert rejects(["idle"], "idle"), "a table that is not a mapping is rejected"
assert rejects(panel, "sleep"), "a starting mode the table does not key is rejected"
print("ok")
