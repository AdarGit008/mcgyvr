from solution import replay_ring_log

assert replay_ring_log(
    2, "overwrite", [["push", "a"], ["push", "b"], ["push", "c"], ["pop"], ["pop"]]
) == {
    "contents": [],
    "journal": ["stored", "stored", "evicted a", "took b", "took c"],
    "lost": 1,
}, "overwrite drops the oldest label and names it in the journal"
assert replay_ring_log(
    2, "refuse", [["push", "a"], ["push", "b"], ["push", "c"], ["pop"], ["pop"]]
) == {
    "contents": [],
    "journal": ["stored", "stored", "refused", "took a", "took b"],
    "lost": 1,
}, "refuse leaves the seated labels untouched and turns the new one away"
assert replay_ring_log(
    1, "overwrite", [["push", "x"], ["push", "y"], ["peek"], ["pop"], ["peek"]]
) == {
    "contents": [],
    "journal": ["stored", "evicted x", "front y", "took y", "bare"],
    "lost": 1,
}, "a one-seat ring always evicts, and a drained ring reads bare"
assert replay_ring_log(
    3,
    "overwrite",
    [["push", "a"], ["push", "b"], ["push", "c"], ["push", "d"], ["push", "e"]],
) == {
    "contents": ["c", "d", "e"],
    "journal": ["stored", "stored", "stored", "evicted a", "evicted b"],
    "lost": 2,
}, "contents run oldest to newest after the ring wraps"
assert replay_ring_log(
    2, "refuse", [["push", "a"], ["push", "b"], ["push", "c"], ["pop"], ["push", "c"]]
) == {
    "contents": ["b", "c"],
    "journal": ["stored", "stored", "refused", "took a", "stored"],
    "lost": 1,
}, "a pop frees a seat that a later push may take"
assert replay_ring_log(
    2, "overwrite", [["push", "a"], ["peek"], ["peek"], ["pop"]]
) == {
    "contents": [],
    "journal": ["stored", "front a", "front a", "took a"],
    "lost": 0,
}, "peeking never removes the label it reads"
assert replay_ring_log(1, "refuse", [["pop"], ["peek"]]) == {
    "contents": [],
    "journal": ["bare", "bare"],
    "lost": 0,
}, "reads against an empty ring cost nothing"
assert replay_ring_log(4, "overwrite", []) == {
    "contents": [],
    "journal": [],
    "lost": 0,
}, "no operations leave an empty journal"
assert replay_ring_log(
    2, "overwrite", [["push", "a"], ["push", "a"], ["push", "a"]]
) == {
    "contents": ["a", "a"],
    "journal": ["stored", "stored", "evicted a"],
    "lost": 1,
}, "repeated labels occupy separate seats"


def rejects(capacity, policy, operations):
    try:
        replay_ring_log(capacity, policy, operations)
    except ValueError:
        return True
    return False


assert rejects(0, "refuse", []), "a zero capacity is rejected"
assert rejects(2.5, "refuse", []), "a fractional capacity is rejected"
assert rejects(2, "drop", []), "an unknown policy is rejected"
assert rejects(2, "refuse", "pop"), "a non-list replay is rejected"
assert rejects(2, "refuse", [[]]), "an empty operation is rejected"
assert rejects(2, "refuse", [["shove", "a"]]), "an unknown name is rejected"
assert rejects(2, "refuse", [["push"]]), "a push with no label is rejected"
assert rejects(2, "refuse", [["push", ""]]), "an empty label is rejected"
assert rejects(2, "refuse", [["pop", "a"]]), "a pop with a label is rejected"
print("ok")
