from solution import dose_totals


def rejects(log):
    try:
        dose_totals(log)
    except Exception:
        return True
    return False


assert dose_totals([["saline", "1.25"], ["saline", "2.75"]]) == {"saline": "4.00"}, "matching places are kept"
assert dose_totals([["dye", "0.5"], ["dye", "0.25"]]) == {"dye": "0.75"}, "the finest pour sets the printed places"
assert dose_totals([["agar", "3"], ["agar", "4"]]) == {"agar": "7"}, "whole pours print without a point"
assert dose_totals([["stock", "-1.5"], ["stock", "0.25"]]) == {"stock": "-1.25"}, "a drawdown may leave the total negative"
assert dose_totals([["buffer", "0.1"], ["buffer", "0.2"]]) == {"buffer": "0.3"}, "tenths add without drift"
assert dose_totals([]) == {}, "an empty log totals nothing"
assert rejects([["dye", "1.2345"]]), "an amount finer than a thousandth is rejected"
print("ok")
