from solution import vend_credit

assert vend_credit([], 25) == 0, "no coins leaves no credit"
assert vend_credit([25], 25) == 0, "one coin at the price drops an item and clears"
assert vend_credit([10, 10], 25) == 20, "credit short of the price stands"
assert vend_credit([10, 10, 10], 25) == 5, "the coin that reaches the price leaves change standing"
assert vend_credit([100], 30) == 10, "one coin drops several items"
assert vend_credit([5, 100], 40) == 25, "earlier credit counts toward the drops"
assert vend_credit([5, 5, 5, 5, 5], 5) == 0, "every coin drops its own item"


def rejects(coins, price):
    try:
        vend_credit(coins, price)
    except ValueError:
        return True
    return False


assert rejects([50], 25), "a coin the acceptor refuses is rejected"
assert rejects([], 0), "a price of zero is rejected"
assert rejects([], 2.5), "a fractional price is rejected"
assert rejects([], 7), "a price off the five-cent step is rejected"
print("ok")
