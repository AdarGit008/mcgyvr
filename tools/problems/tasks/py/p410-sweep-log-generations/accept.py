from solution import sweep_log_generations

assert sweep_log_generations(
    "app.log",
    [
        {"name": "app.log", "bytes": 1200, "days": 2},
        {"name": "app.log.1", "bytes": 900, "days": 5},
        {"name": "app.log.2", "bytes": 800, "days": 9},
        {"name": "app.log.3", "bytes": 700, "days": 20},
    ],
    {"rotateAt": 1000, "keep": 3, "maxDays": 14},
) == {
    "kept": ["app.log", "app.log.1", "app.log.2", "app.log.3"],
    "rotated": [
        ["app.log", "app.log.1"],
        ["app.log.1", "app.log.2"],
        ["app.log.2", "app.log.3"],
        ["app.log.3", "app.log.4"],
    ],
    "deleted": ["app.log.4"],
}, "a full rotation with the oldest copy pushed past keep"

assert sweep_log_generations(
    "app.log",
    [
        {"name": "app.log", "bytes": 500, "days": 1},
        {"name": "app.log.1", "bytes": 900, "days": 30},
        {"name": "app.log.2", "bytes": 800, "days": 3},
    ],
    {"rotateAt": 1000, "keep": 5, "maxDays": 14},
) == {
    "kept": ["app.log", "app.log.2"],
    "rotated": [],
    "deleted": ["app.log.1"],
}, "too small to rotate, and age leaves a gap behind"

assert sweep_log_generations(
    "j", [{"name": "j", "bytes": 5, "days": 10}], {"rotateAt": 1, "keep": 2, "maxDays": 3}
) == {
    "kept": ["j"],
    "rotated": [["j", "j.1"]],
    "deleted": ["j.1"],
}, "a stale live file is rotated and then thrown out at once"

assert sweep_log_generations(
    "x",
    [
        {"name": "x", "bytes": 100, "days": 0},
        {"name": "x.1", "bytes": 40, "days": 1},
        {"name": "x.2", "bytes": 40, "days": 9},
        {"name": "x.3", "bytes": 40, "days": 2},
    ],
    {"rotateAt": 100, "keep": 2, "maxDays": 5},
) == {
    "kept": ["x", "x.1", "x.2"],
    "rotated": [["x", "x.1"], ["x.1", "x.2"], ["x.2", "x.3"], ["x.3", "x.4"]],
    "deleted": ["x.3", "x.4"],
}, "reaching rotateAt exactly still rotates, and keep sheds two"

assert sweep_log_generations(
    "s", [{"name": "s", "bytes": 3, "days": 0}], {"rotateAt": 10, "keep": 1, "maxDays": 1}
) == {"kept": ["s"], "rotated": [], "deleted": []}, "a lone live file below the trigger"

assert sweep_log_generations(
    "s", [{"name": "s", "bytes": 30, "days": 0}], {"rotateAt": 10, "keep": 1, "maxDays": 1}
) == {
    "kept": ["s", "s.1"],
    "rotated": [["s", "s.1"]],
    "deleted": [],
}, "a lone live file over the trigger gains a copy"

sound = [{"name": "q", "bytes": 1, "days": 1}]
plain = {"rotateAt": 10, "keep": 2, "maxDays": 7}


def rejects(base, files, rules):
    try:
        sweep_log_generations(base, files, rules)
    except ValueError:
        return True
    return False


assert rejects("", sound, plain), "an empty live name"
assert rejects(5, sound, plain), "a live name that is no string"
assert rejects("q", 5, plain), "files that are not a list"
assert rejects("q", [], plain), "no live file at all"
assert rejects("q", [7], plain), "a file that is not a record"
assert rejects("q", [{"name": 3, "bytes": 1, "days": 1}], plain), "a name that is not a string"
assert rejects(
    "q", [{"name": "q", "bytes": 1, "days": 1}, {"name": "other", "bytes": 1, "days": 1}], plain
), "a stray name"
assert rejects(
    "q", [{"name": "q", "bytes": 1, "days": 1}, {"name": "q.0", "bytes": 1, "days": 1}], plain
), "a copy numbered nothing"
assert rejects(
    "q", [{"name": "q", "bytes": 1, "days": 1}, {"name": "q.01", "bytes": 1, "days": 1}], plain
), "a copy number with a leading zero"
assert rejects(
    "q", [{"name": "q", "bytes": 1, "days": 1}, {"name": "q.2", "bytes": 1, "days": 1}], plain
), "a gap in the copy numbers"
assert rejects(
    "q", [{"name": "q", "bytes": 1, "days": 1}, {"name": "q", "bytes": 2, "days": 2}], plain
), "one name twice"
assert rejects("q", [{"name": "q", "bytes": -1, "days": 1}], plain), "negative bytes"
assert rejects("q", [{"name": "q", "bytes": 1, "days": 1.5}], plain), "fractional days"
assert rejects("q", sound, 4), "rules that are not a record"
assert rejects("q", sound, {"rotateAt": 0, "keep": 2, "maxDays": 7}), "a trigger of nothing"
assert rejects("q", sound, {"rotateAt": 10, "keep": 0, "maxDays": 7}), "keeping nothing"
assert rejects("q", sound, {"rotateAt": 10, "keep": 2, "maxDays": 0}), "an age limit of nothing"
print("ok")
