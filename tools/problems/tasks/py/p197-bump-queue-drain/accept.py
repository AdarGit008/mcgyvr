from solution import bump_queue_drain


def t(identifier, filed, grade):
    return {"id": identifier, "filed": filed, "grade": grade}


def rejects(tickets, start, bump_every):
    try:
        bump_queue_drain(tickets, start, bump_every)
    except ValueError:
        return True
    return False


assert bump_queue_drain([t("only", 0, 0)], 0, 4) == [
    "only"
], "one ticket is handled at the start minute"

assert bump_queue_drain([t("t1", 0, 2), t("t2", 0, 5)], 0, 4) == [
    "t2",
    "t1",
], "the heavier grade goes first when no bump has landed"

assert bump_queue_drain([t("A", 0, 0), t("B", 9, 2)], 9, 3) == [
    "A",
    "B",
], "three bumps carry a lowly ticket past a fresh heavier one"

assert bump_queue_drain([t("A", 0, 0), t("B", 0, 9)], 20, 1) == [
    "A",
    "B",
], "the ceiling flattens both urgencies so the id decides"

assert bump_queue_drain([t("A", 0, 1), t("B", 2, 9), t("C", 0, 0)], 0, 5) == [
    "A",
    "C",
    "B",
], "a ticket cannot be handled before the minute it was filed"

assert bump_queue_drain([t("A", 5, 1), t("B", 5, 3)], 0, 4) == [
    "B",
    "A",
], "minutes with nothing eligible pass by"

assert bump_queue_drain([t("A", 0, 3), t("B", 4, 4)], 4, 4) == [
    "A",
    "B",
], "equal urgency falls to the ticket filed earlier"

assert bump_queue_drain([t("zulu", 0, 2), t("alpha", 0, 2)], 0, 4) == [
    "alpha",
    "zulu",
], "equal urgency and equal filing falls to the id"

assert rejects([], 0, 4), "an empty batch is rejected"
assert rejects(["t1"], 0, 4), "a ticket that is not a mapping is rejected"
assert rejects([{"filed": 0, "grade": 1}], 0, 4), "a ticket with no id is rejected"
assert rejects([t("dup", 0, 1), t("dup", 1, 2)], 0, 4), "a repeated id is rejected"
assert rejects([t("A", -1, 1)], 0, 4), "a negative filed minute is rejected"
assert rejects([t("A", 0, 10)], 0, 4), "a grade above nine is rejected"
assert rejects([t("A", 0, 1)], -3, 4), "a negative start minute is rejected"
assert rejects([t("A", 0, 1)], 0, 0), "a bump interval of zero is rejected"

print("ok")
