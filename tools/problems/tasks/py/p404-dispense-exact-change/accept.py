from solution import dispense_exact_change

till = [[25, 4], [10, 3], [5, 2], [1, 10]]

assert dispense_exact_change(0, till) == [], "nothing owed pays nothing"
assert dispense_exact_change(3, till) == [[1, 3]], "smallest face only"
assert dispense_exact_change(8, till) == [[5, 1], [1, 3]], "two faces"
assert dispense_exact_change(30, till) == [[25, 1], [5, 1]], "fewest coins beats the tens"
assert dispense_exact_change(40, till) == [[25, 1], [10, 1], [5, 1]], "three faces"
assert dispense_exact_change(60, till) == [[25, 2], [10, 1]], "repeated largest face"
assert dispense_exact_change(100, till) == [[25, 4]], "the whole stock of one face"

scarce = [[25, 1], [10, 0], [5, 3]]
assert dispense_exact_change(15, scarce) == [[5, 3]], "an empty stock is unusable"
assert dispense_exact_change(35, scarce) == [[25, 1], [5, 2]], "the stocked faces carry it"

tied = [[5, 2], [3, 5], [2, 5], [1, 10]]
assert dispense_exact_change(6, tied) == [[5, 1], [1, 1]], "a tie goes to the larger face"

odd = [[9, 1], [6, 2], [5, 1], [4, 1], [1, 3]]
assert dispense_exact_change(10, odd) == [[9, 1], [1, 1]], "the greedy face wins a real tie"
assert dispense_exact_change(12, odd) == [[6, 2]], "greedy would fail here"


def rejects(amount, hopper):
    try:
        dispense_exact_change(amount, hopper)
    except ValueError:
        return True
    return False


assert rejects(200, till), "beyond the stock is refused"
assert rejects(7, [[5, 10]]), "no exact combination"
assert rejects(-1, till), "a negative amount is refused"
assert rejects(2.5, till), "a fractional amount is refused"
assert rejects("10", till), "a non-number amount is refused"
assert rejects(100001, till), "an amount over the ceiling"
assert rejects(5, 5), "a hopper that is not a list"
assert rejects(5, []), "a hopper with no faces"
assert rejects(5, [[25]]), "an entry that is not a pair"
assert rejects(5, [[0, 3]]), "a face value of nothing"
assert rejects(5, [[2.5, 3]]), "a fractional face value"
assert rejects(5, [[5, -1]]), "a negative stock"
assert rejects(5, [[5, 1], [5, 2]]), "one face listed twice"
print("ok")
