from solution import trace_print_job

assert trace_print_job([], 0) == {
    "state": "queued",
    "pauses": 0,
    "jams": 0,
    "path": ["queued"],
}, "no events leaves the job queued"
assert trace_print_job(["start"], 0) == {
    "state": "printing",
    "pauses": 0,
    "jams": 0,
    "path": ["queued", "printing"],
}, "start moves to printing"
assert trace_print_job(["start", "finish"], 0) == {
    "state": "done",
    "pauses": 0,
    "jams": 0,
    "path": ["queued", "printing", "done"],
}, "a clean run finishes"
assert trace_print_job(["start", "pause"], 1) == {
    "state": "paused",
    "pauses": 1,
    "jams": 0,
    "path": ["queued", "printing", "paused"],
}, "pause is counted"
assert trace_print_job(["start", "pause", "resume"], 1) == {
    "state": "printing",
    "pauses": 1,
    "jams": 0,
    "path": ["queued", "printing", "paused", "printing"],
}, "resume returns to printing"
assert trace_print_job(["start", "jam", "clear", "finish"], 0) == {
    "state": "done",
    "pauses": 0,
    "jams": 1,
    "path": ["queued", "printing", "blocked", "printing", "done"],
}, "a jam is cleared and counted"
assert trace_print_job(["cancel"], 0) == {
    "state": "cancelled",
    "pauses": 0,
    "jams": 0,
    "path": ["queued", "cancelled"],
}, "cancel applies while queued"
assert trace_print_job(["start", "jam", "cancel"], 0) == {
    "state": "cancelled",
    "pauses": 0,
    "jams": 1,
    "path": ["queued", "printing", "blocked", "cancelled"],
}, "cancel applies while blocked"


def rejects(events, pause_limit):
    try:
        trace_print_job(events, pause_limit)
    except ValueError:
        return True
    return False


assert rejects(["eject"], 0), "unknown event is rejected"
assert rejects(["finish"], 0), "finish before start is rejected"
assert rejects(["start", "finish", "start"], 0), "no event applies after done"
assert rejects(["start", "pause", "resume", "pause"], 1), "pause past the cap"
assert rejects([42], 0), "non-string event is rejected"
assert rejects(["start"], 1.5), "fractional pause cap is rejected"
print("ok")
