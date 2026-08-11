from solution import hop_chain

assert hop_chain([["a", "b"], ["b", "c"]]) is True, "two hops meet"
assert hop_chain([["a", "b"], ["c", "d"]]) is False, "two hops do not meet"
assert hop_chain([["a", "b"]]) is True, "a single hop is unbroken"
assert hop_chain([]) is True, "no hops at all"
assert hop_chain([["a", "b"], ["b", "c"], ["c", "d"]]) is True, "three hops in a row"
assert (
    hop_chain([["a", "b"], ["b", "c"], ["x", "d"]]) is False
), "the last hop breaks the chain"
print("ok")
