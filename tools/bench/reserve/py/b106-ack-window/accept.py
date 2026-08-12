from solution import link_ack, link_send, new_link


def rejects(fn, *args):
    try:
        fn(*args)
    except Exception:
        return True
    return False


assert new_link(3) == {
    "size": 3,
    "next": 0,
    "pending": [],
    "delivered": 0,
}, "a fresh link is empty"
link = new_link(3)
link_send(link, "syn")
assert link_send(link, "hello") == 1, "sends take sequence numbers in order"
link_send(link, "world")
assert rejects(link_send, link, "late"), "a full window refuses to send"
assert link_ack(link, 0) == ["syn"], "acking the oldest frame frees it"
assert link == {
    "size": 3,
    "next": 3,
    "pending": [[1, "hello"], [2, "world"]],
    "delivered": 1,
}, "the freed frame leaves pending and delivered grows"
assert link_ack(link, -1) == [], "an ack of -1 frees nothing"
assert link_ack(link, 2) == [
    "hello",
    "world",
], "a cumulative ack frees every covered frame oldest first"
assert link["delivered"] == 3, "delivered counts every freed frame"
assert link_send(link, "again") == 3, "sequence numbers are never reused"
assert rejects(link_ack, link, 4), "acking an unsent frame is rejected"
assert rejects(link_ack, link, 1.5), "a fractional ack is rejected"
assert rejects(link_ack, link, -2), "an ack below -1 is rejected"
assert rejects(new_link, 0), "a zero window size is rejected"
assert rejects(link_send, new_link(1), ""), "an empty payload is rejected"
print("ok")
