from solution import rack_units, zone_stock

STORE = {
    "name": "dock",
    "bins": {"bolt": 2},
    "children": [
        {
            "name": "north",
            "bins": {"washer": 5},
            "children": [{"name": "north-1", "bins": {"bolt": 3}, "children": []}],
        },
        {"name": "annex", "bins": {"bolt": 1, "washer": 2}, "children": []},
    ],
}

assert zone_stock({"name": "solo", "bins": {"bolt": 4}, "children": []}, "bolt") == {
    "total": 4,
    "holders": ["solo"],
}, "a lone zone holds its own stock"
assert zone_stock(STORE, "bolt") == {
    "total": 6,
    "holders": ["dock", "north-1", "annex"],
}, "holders come in visiting order, each zone before its children"
assert zone_stock(STORE, "washer") == {
    "total": 7,
    "holders": ["north", "annex"],
}, "zones without the sku stay out of holders"
assert zone_stock(STORE, "gasket") == {
    "total": 0,
    "holders": [],
}, "an unknown sku totals zero"
assert zone_stock(
    {
        "name": "hub",
        "bins": {},
        "children": [{"name": "cage", "bins": {"bolt": 9}, "children": []}],
    },
    "bolt",
) == {"total": 9, "holders": ["cage"]}, "stock deep in one child is found"
assert rack_units({"bolt": 4}, "bolt") == 4, "rack_units reads a listed sku"
assert rack_units({"bolt": 4}, "nut") == 0, "rack_units reads an absent sku as zero"


def rejects(zone, sku):
    try:
        zone_stock(zone, sku)
    except Exception:
        return True
    return False


assert rejects(
    {
        "name": "dock",
        "bins": {},
        "children": [{"name": "dock", "bins": {}, "children": []}],
    },
    "bolt",
), "one name on two zones is rejected"
assert rejects(
    {"name": "a", "bins": {"bolt": 0}, "children": []}, "bolt"
), "a zero count is rejected"
assert rejects(
    {"name": "a", "bins": {"bolt": 2.5}, "children": []}, "bolt"
), "a fractional count is rejected"
assert rejects([], "bolt"), "a zone that is not a record is rejected"
assert rejects({"bins": {}, "children": []}, "bolt"), "a missing name is rejected"
assert rejects({"name": "a", "bins": 3, "children": []}, "bolt"), "bins must be a mapping"
assert rejects(
    {"name": "a", "bins": {}, "children": "none"}, "bolt"
), "children must be a list"


def helper_rejects(bins, sku):
    try:
        rack_units(bins, sku)
    except Exception:
        return True
    return False


assert helper_rejects({}, ""), "an empty sku is rejected"
print("ok")
