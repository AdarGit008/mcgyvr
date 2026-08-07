from solution import invoice_total

assert invoice_total([{"qty": 2, "unit": 500, "discount": 0}], 0) == {
    "subtotal": 1000,
    "tax": 0,
    "total": 1000,
}, "no discount and no tax is plain multiplication"
assert invoice_total([{"qty": 1, "unit": 999, "discount": 250}], 0) == {
    "subtotal": 974,
    "tax": 0,
    "total": 974,
}, "24.975 cents of rebate round half up to 25"
assert (
    invoice_total(
        [
            {"qty": 1, "unit": 5, "discount": 1000},
            {"qty": 1, "unit": 5, "discount": 1000},
        ],
        0,
    )["subtotal"]
    == 8
), "per-line rounding: two nets of 4, not a pooled 9"
assert (
    invoice_total([{"qty": 1, "unit": 2, "discount": 2500}], 0)["subtotal"] == 1
), "an exact half cent of rebate rounds up"
assert invoice_total([{"qty": 3, "unit": 1, "discount": 0}], 1667) == {
    "subtotal": 3,
    "tax": 1,
    "total": 4,
}, "tax of 0.5001 cents rounds half up to 1"
assert invoice_total([{"qty": 1, "unit": 2, "discount": 0}], 2500) == {
    "subtotal": 2,
    "tax": 1,
    "total": 3,
}, "an exact half cent of tax rounds up"
assert (
    invoice_total([{"qty": 4, "unit": 250, "discount": 10000}], 5000)["total"] == 0
), "a full discount leaves nothing to tax"
assert invoice_total(
    [
        {"qty": 2, "unit": 1050, "discount": 0},
        {"qty": 1, "unit": 333, "discount": 3333},
    ],
    825,
) == {
    "subtotal": 2322,
    "tax": 192,
    "total": 2514,
}, "a mixed invoice totals correctly end to end"


def rejects(lines, rate):
    try:
        invoice_total(lines, rate)
    except ValueError:
        return True
    return False


assert rejects([], 0), "an empty invoice is rejected"
assert rejects([{"qty": 0, "unit": 100, "discount": 0}], 0), "zero qty is rejected"
assert rejects([{"qty": 1, "unit": -5, "discount": 0}], 0), (
    "negative unit price is rejected"
)
assert rejects([{"qty": 1, "unit": 100, "discount": 10001}], 0), (
    "discount above 10000 basis points is rejected"
)
assert rejects([{"qty": 1, "unit": 100, "discount": 0}], -1), (
    "negative tax rate is rejected"
)
assert rejects([{"qty": 1.5, "unit": 100, "discount": 0}], 0), (
    "fractional qty is rejected"
)
print("ok")
