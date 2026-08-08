from solution import apply_discount_bands


def rule(code, band, mode, amount, floor, solo):
    return {
        "code": code,
        "band": band,
        "mode": mode,
        "amount": amount,
        "floor": floor,
        "solo": solo,
    }


def rejects(basket, rules):
    try:
        apply_discount_bands(basket, rules)
    except ValueError:
        return True
    return False


CART = [["mug", 450, 2], ["pot", 1200, 1]]

assert apply_discount_bands(CART, []) == {
    "total": 2100,
    "applied": [],
}, "no rules leaves the subtotal alone"
assert apply_discount_bands(
    CART,
    [
        rule("WELCOME", "intro", "share", 10, 0, False),
        rule("HELLO", "intro", "share", 25, 0, False),
        rule("BULK", "volume", "flat", 500, 2000, False),
        rule("CHIP", "volume", "flat", 300, 1500, False),
        rule("CLOSE", "final", "share", 5, 0, True),
        rule("EXTRA", "bonus", "flat", 100, 0, False),
    ],
) == {
    "total": 1511,
    "applied": ["WELCOME", "CHIP", "CLOSE"],
}, "bands, floors and a solo rule together"
assert apply_discount_bands([["x", 300, 1]], [rule("BIG", "a", "flat", 500, 0, False)]) == {
    "total": 0,
    "applied": ["BIG"],
}, "a flat cut never digs past the running figure"
assert apply_discount_bands(
    [],
    [
        rule("A", "b1", "share", 10, 0, False),
        rule("B", "b1", "flat", 700, 0, False),
        rule("C", "b2", "flat", 700, 0, False),
    ],
) == {
    "total": 0,
    "applied": ["A", "C"],
}, "a bite claims its band even when the cut is nothing"
assert apply_discount_bands(
    [["x", 1000, 1]],
    [rule("P", "z", "flat", 900, 5000, False), rule("Q", "z", "share", 20, 0, False)],
) == {
    "total": 800,
    "applied": ["Q"],
}, "a rule held back by its floor does not claim the band"
assert apply_discount_bands([["x", 999, 1]], [rule("R", "a", "share", 33, 0, False)]) == {
    "total": 670,
    "applied": ["R"],
}, "a part of a cent is dropped from a share cut"
assert apply_discount_bands(
    [["x", 1000, 1]],
    [rule("S", "a", "share", 50, 0, True), rule("T", "b", "flat", 100, 0, False)],
) == {"total": 500, "applied": ["S"]}, "a solo bite passes over every rule behind it"
assert apply_discount_bands(
    [["x", 1000, 1]],
    [rule("S", "a", "flat", 100, 5000, True), rule("T", "b", "flat", 100, 0, False)],
) == {"total": 900, "applied": ["T"]}, "a solo rule that never bites blocks nothing"
assert apply_discount_bands(
    [["x", 500, 2]],
    [rule("A", "a", "share", 50, 0, False), rule("B", "b", "flat", 100, 600, False)],
) == {
    "total": 500,
    "applied": ["A"],
}, "a floor is read against the running figure, not the subtotal"
assert apply_discount_bands([["x", 100, 3], ["x", 50, 2]], []) == {
    "total": 400,
    "applied": [],
}, "one sku may appear on two lines"

ONE = [rule("A", "a", "flat", 100, 0, False)]
assert rejects([["x", 300]], ONE), "a basket line that is not a triple is refused"
assert rejects([["", 300, 1]], ONE), "an empty sku is refused"
assert rejects([["x", -1, 1]], ONE), "negative cents are refused"
assert rejects([["x", 1.5, 1]], ONE), "fractional cents are refused"
assert rejects([["x", 300, 0]], ONE), "a count under one is refused"
assert rejects(
    CART, [{"code": "A", "band": "a", "mode": "flat", "amount": 1, "floor": 0}]
), "a rule missing a key is refused"
assert rejects(
    CART, [dict(rule("A", "a", "flat", 1, 0, False), extra=1)]
), "a rule carrying an extra key is refused"
assert rejects(
    CART, [rule("A", "a", "flat", 1, 0, False), rule("A", "b", "flat", 1, 0, False)]
), "two rules sharing a code are refused"
assert rejects(CART, [rule("A", "a", "half", 1, 0, False)]), "an unknown mode is refused"
assert rejects(CART, [rule("A", "a", "share", 0, 0, False)]), "a share of nought is refused"
assert rejects(CART, [rule("A", "a", "share", 101, 0, False)]), "a share past 100 is refused"
assert rejects(CART, [rule("A", "a", "flat", 0, 0, False)]), "a flat amount of nought is refused"
assert rejects(CART, [rule("A", "a", "flat", 1, -1, False)]), "a negative floor is refused"
assert rejects(
    CART, [rule("A", "a", "flat", 1, 0, "yes")]
), "a solo flag that is not a boolean is refused"
assert rejects(CART, [["A", "a", "flat", 1, 0, False]]), "a rule that is not a mapping is refused"
print("ok")
