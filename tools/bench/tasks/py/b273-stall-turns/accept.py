from solution import stall_turns

assert stall_turns([2, 2], 2) == 2, "one turn each"
assert stall_turns([3], 2) == 2, "a spillover takes another turn"
assert stall_turns([1, 1, 1], 5) == 3, "a turn is never shared"
assert stall_turns([0, 4], 4) == 1, "wanting nothing takes no turn"
assert stall_turns([], 3) == 0, "no customers, no turns"
assert stall_turns([7], 3) == 3, "three turns for seven items"
print("ok")
