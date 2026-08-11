from solution import queue_call

assert queue_call(["a", "b", "c"], [], "a") == "b", "the very next ticket"
assert queue_call(["a", "b", "c"], ["b"], "a") == "c", "a withdrawn ticket is passed"
assert queue_call(["a", "b"], [], "b") is None, "nothing follows the last"
assert queue_call(["a", "b"], ["b"], "a") is None, "the only follower withdrew"
assert (
    queue_call(["a", "b", "c", "d"], ["b", "c"], "a") == "d"
), "two withdrawals in a row"
assert queue_call(["a"], [], "a") is None, "a queue of one"
print("ok")
