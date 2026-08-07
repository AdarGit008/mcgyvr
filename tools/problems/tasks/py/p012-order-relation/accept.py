from solution import order_relation

chain = [["a", "b"], ["b", "c"], ["c", "d"]]
assert order_relation(chain, "a", "c") == "before", "transitive before"
assert order_relation(chain, "d", "b") == "after", "transitive after"
assert order_relation(chain, "a", "b") == "before", "direct edge"
fork = [["a", "b"], ["a", "c"]]
assert order_relation(fork, "b", "c") == "unordered", "siblings are unordered"
loop = [["p", "q"], ["q", "r"], ["r", "p"]]
assert order_relation(loop, "p", "r") == "both", "cycle reaches both ways"
islands = [["a", "b"], ["c", "d"]]
assert order_relation(islands, "a", "d") == "unordered", "disconnected items"
assert order_relation([["m", "n"], ["n", "m"]], "m", "n") == "both", "two-cycle"


def rejects(pairs, x, y):
    try:
        order_relation(pairs, x, y)
    except ValueError:
        return True
    return False


assert rejects(chain, "b", "b"), "equal query items rejected"
assert rejects(chain, "a", "zz"), "unknown item rejected"
print("ok")
