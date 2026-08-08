from solution import level_payment_schedule

assert level_payment_schedule(100000, 100, 30000, 4) == [
    [30000, 1000, 29000, 71000],
    [30000, 710, 29290, 41710],
    [30000, 417, 29583, 12127],
    [12248, 121, 12127, 0],
], "four periods, the last one smaller than the level payment"
assert level_payment_schedule(100000, 100, 15000, 3) == [
    [15000, 1000, 14000, 86000],
    [15000, 860, 14140, 71860],
    [72579, 719, 71860, 0],
], "a short term makes the closing period a balloon far above the payment"
assert level_payment_schedule(5000, 0, 3000, 10) == [
    [3000, 0, 3000, 2000],
    [2000, 0, 2000, 0],
], "a debt cleared early stops short of the term"
assert level_payment_schedule(50, 100, 40, 1) == [
    [51, 1, 50, 0]
], "a single period settles the whole debt with its charge"
assert level_payment_schedule(149, 100, 100, 2) == [
    [100, 1, 99, 50],
    [51, 1, 50, 0],
], "an exact half cent rounds up and a charge below half a cent rounds to nothing"
assert level_payment_schedule(1000, 0, 250, 4) == [
    [250, 0, 250, 750],
    [250, 0, 250, 500],
    [250, 0, 250, 250],
    [250, 0, 250, 0],
], "a rate of zero splits the debt evenly and lands exactly on the term"
assert level_payment_schedule(700, 0, 9000, 6) == [
    [700, 0, 700, 0]
], "a payment larger than the debt closes the schedule in one row"
assert len(level_payment_schedule(100000, 100, 30000, 9)) == 4, "the row count is the periods used"


def rejects(opening, rate, payment, terms):
    try:
        level_payment_schedule(opening, rate, payment, terms)
    except ValueError:
        return True
    return False


assert rejects(0, 100, 500, 3), "an opening of zero is rejected"
assert rejects(-100, 100, 500, 3), "a negative opening is rejected"
assert rejects(1000.5, 100, 500, 3), "a fractional opening is rejected"
assert rejects(1000, -1, 500, 3), "a negative rate is rejected"
assert rejects(1000, 100, 0, 3), "a payment of zero is rejected"
assert rejects(1000, 100, 500, 0), "a term of zero is rejected"
assert rejects(1000, 100, 500, 2.5), "a fractional term is rejected"
assert rejects(100000, 100, 1000, 5), "a payment equal to the first charge is rejected"
assert rejects(100000, 100, 500, 5), "a payment beneath the first charge is rejected"
print("ok")
