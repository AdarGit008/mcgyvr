from solution import check_guarantee_claim

assert check_guarantee_claim("2023-05-10", 24, 30, "2025-05-10") == {
    "plain": "2025-05-10",
    "last": "2025-06-09",
    "verdict": "inside",
    "over": 0,
}, "a complaint on the very day the backing runs out is still inside it"
assert check_guarantee_claim("2023-05-10", 24, 30, "2025-05-11") == {
    "plain": "2025-05-10",
    "last": "2025-06-09",
    "verdict": "grace",
    "over": 0,
}, "the day after the backing runs out falls in the allowance"
assert check_guarantee_claim("2023-05-10", 24, 30, "2025-06-09") == {
    "plain": "2025-05-10",
    "last": "2025-06-09",
    "verdict": "grace",
    "over": 0,
}, "the last day of the allowance is still heard"
assert check_guarantee_claim("2023-05-10", 24, 30, "2025-06-10") == {
    "plain": "2025-05-10",
    "last": "2025-06-09",
    "verdict": "lapsed",
    "over": 1,
}, "one day past the allowance is a day over"
assert check_guarantee_claim("2024-02-29", 12, 0, "2025-03-01") == {
    "plain": "2025-02-28",
    "last": "2025-02-28",
    "verdict": "lapsed",
    "over": 1,
}, "a leap day sale runs out on the 28th the year after"
assert check_guarantee_claim("2023-05-10", 24, 30, "2023-05-09") == {
    "plain": "2025-05-10",
    "last": "2025-06-09",
    "verdict": "early",
    "over": 0,
}, "a complaint before the sale is early"
assert check_guarantee_claim("2020-12-31", 2, 5, "2021-03-05") == {
    "plain": "2021-02-28",
    "last": "2021-03-05",
    "verdict": "grace",
    "over": 0,
}, "a short month pulls the run-out back to its final day"
assert check_guarantee_claim("2023-01-01", 240, 365, "2043-01-01") == {
    "plain": "2043-01-01",
    "last": "2044-01-01",
    "verdict": "inside",
    "over": 0,
}, "twenty years of backing reach across five leap years"


def rejects(sold, months, grace, claim):
    try:
        check_guarantee_claim(sold, months, grace, claim)
    except ValueError:
        return True
    return False


assert rejects("2023-5-10", 12, 0, "2024-01-01"), "an unpadded month"
assert rejects("2023-02-30", 12, 0, "2024-01-01"), "a day that never was"
assert rejects("3000-01-01", 12, 0, "3000-06-01"), "a year past 2999"
assert rejects("2023-01-01", 0, 0, "2024-01-01"), "no months backed"
assert rejects("2023-01-01", 241, 0, "2024-01-01"), "too many months"
assert rejects("2023-01-01", 12, -1, "2024-01-01"), "a negative allowance"
assert rejects("2023-01-01", 12, 366, "2024-01-01"), "an allowance past a year"
assert rejects("2023-01-01", 12.5, 0, "2024-01-01"), "months must be whole"
assert rejects("2023-01-01", 12, 0, 20240101), "the complaint day must be a string"
print("ok")
