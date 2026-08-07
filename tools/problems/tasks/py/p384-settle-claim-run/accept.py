from solution import settle_claim_run

standard = {"deductible": 50000, "coinsurance": 20, "cap": 150000}

assert settle_claim_run([30000, 40000, 500000, 20000], standard) == [
    [30000, 0, 20000, 30000],
    [24000, 16000, 0, 54000],
    [96000, 404000, 0, 150000],
    [0, 20000, 0, 150000],
], "a full run walks deductible, then coinsurance, then the cap"
assert settle_claim_run([], standard) == [], "a run with no claims settles nothing"
assert settle_claim_run([0], standard) == [
    [0, 0, 50000, 0]
], "a claim of zero cents moves nothing and wears nothing down"
assert settle_claim_run([101], {"deductible": 0, "coinsurance": 50, "cap": 1000000}) == [
    [51, 50, 0, 51]
], "an exact half cent of coinsurance is carried upward"
assert settle_claim_run([500], {"deductible": 100, "coinsurance": 0, "cap": 1000}) == [
    [100, 400, 0, 100]
], "a coinsurance of zero leaves the member only the deductible"
assert settle_claim_run([500], {"deductible": 0, "coinsurance": 100, "cap": 300}) == [
    [300, 200, 0, 300]
], "a coinsurance of one hundred still stops at the cap"
assert settle_claim_run(
    [500, 2000, 1000], {"deductible": 1000, "coinsurance": 50, "cap": 1200}
) == [
    [500, 0, 500, 500],
    [700, 1300, 0, 1200],
    [0, 1000, 0, 1200],
], "the deductible is worn down by what it swallowed, not by what was paid"
assert settle_claim_run([700, 700], {"deductible": 1000, "coinsurance": 25, "cap": 5000}) == [
    [700, 0, 300, 700],
    [400, 300, 0, 1100],
], "a claim may straddle the end of the deductible"
assert settle_claim_run([3], {"deductible": 0, "coinsurance": 25, "cap": 900}) == [
    [1, 2, 0, 1]
], "a quarter of three cents rounds down to one"
assert settle_claim_run([100, 100], {"deductible": 100, "coinsurance": 50, "cap": 100}) == [
    [100, 0, 0, 100],
    [0, 100, 0, 100],
], "a cap equal to the deductible closes the run at once"


def rejects(claims, plan):
    try:
        settle_claim_run(claims, plan)
    except ValueError:
        return True
    return False


assert rejects("100", standard), "a non-list run is rejected"
assert rejects([100, -1], standard), "a negative claim is rejected"
assert rejects([1.5], standard), "a fractional claim is rejected"
assert rejects([100], None), "a missing plan is rejected"
assert rejects([100], [0, 20, 100]), "a plan given as a list is rejected"
assert rejects([100], {"deductible": 0, "coinsurance": 20}), "a plan with no cap is rejected"
assert rejects(
    [100], {"deductible": 0, "coinsurance": 101, "cap": 900}
), "a coinsurance above one hundred is rejected"
assert rejects(
    [100], {"deductible": -1, "coinsurance": 20, "cap": 900}
), "a negative deductible is rejected"
assert rejects(
    [100], {"deductible": 900, "coinsurance": 20, "cap": 400}
), "a cap below the deductible is rejected"
print("ok")
