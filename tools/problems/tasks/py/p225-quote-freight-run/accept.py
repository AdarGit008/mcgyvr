from solution import quote_freight_run

BANDS = [
    {"from": 0, "perKilo": 100},
    {"from": 5, "perKilo": 80},
    {"from": 20, "perKilo": 50},
]


def rejects(bands, kilos):
    try:
        quote_freight_run(bands, kilos)
    except ValueError:
        return True
    return False


assert quote_freight_run(BANDS, 7) == {
    "split": [500, 160, 0],
    "cents": 660,
}, "the run crosses into the second band and stops there"

assert quote_freight_run(BANDS, 5) == {
    "split": [500, 0, 0],
    "cents": 500,
}, "a weight landing on a band's start leaves that band with nothing yet"

assert quote_freight_run(BANDS, 4) == {
    "split": [400, 0, 0],
    "cents": 400,
}, "a run wholly inside the first band"

assert quote_freight_run(BANDS, 1) == {
    "split": [100, 0, 0],
    "cents": 100,
}, "the smallest consignment there is"

assert quote_freight_run(BANDS, 20) == {
    "split": [500, 1200, 0],
    "cents": 1700,
}, "the middle band charges its whole stretch and no more"

assert quote_freight_run(BANDS, 21) == {
    "split": [500, 1200, 50],
    "cents": 1750,
}, "the last band picks up everything beyond its start"

assert quote_freight_run([{"from": 0, "perKilo": 250}], 3) == {
    "split": [750],
    "cents": 750,
}, "one band charges the whole run"

assert quote_freight_run([{"from": 0, "perKilo": 0}], 9) == {
    "split": [0],
    "cents": 0,
}, "a free rate charges nothing however heavy the run"

assert rejects("bands", 3), "bands that are not a list are rejected"
assert rejects([], 3), "an empty band list is rejected"
assert rejects([["from", 0]], 3), "a band that is not a mapping is rejected"
assert rejects([{"from": 1, "perKilo": 100}], 3), "a first band starting above nought is rejected"
assert rejects(
    [{"from": 0, "perKilo": 1}, {"from": 0, "perKilo": 2}], 3
), "starting weights that do not climb are rejected"
assert rejects(
    [{"from": 0, "perKilo": 1}, {"from": 4, "perKilo": 2}, {"from": 2, "perKilo": 3}], 3
), "a starting weight that falls back is rejected"
assert rejects([{"from": 0, "perKilo": -1}], 3), "a negative rate is rejected"
assert rejects([{"from": 0, "perKilo": 1.5}], 3), "a fractional rate is rejected"
assert rejects([{"from": "0", "perKilo": 1}], 3), "a starting weight that is not a number is rejected"
assert rejects(BANDS, 0), "a weightless consignment is rejected"
assert rejects(BANDS, 2.5), "a fractional weight is rejected"
assert rejects(BANDS, "3"), "a weight that is not a number is rejected"

print("ok")
