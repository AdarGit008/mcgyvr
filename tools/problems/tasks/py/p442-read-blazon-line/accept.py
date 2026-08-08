from solution import read_blazon_line


def rejects(*args):
    try:
        read_blazon_line(*args)
    except ValueError:
        return True
    return False


assert read_blazon_line("azure") == {
    "field": {"cut": "plain", "tinctures": ["azure"]},
    "charges": [],
}, "a bare tincture is a plain field with no charges"

assert read_blazon_line("or; a lion gules") == {
    "field": {"cut": "plain", "tinctures": ["or"]},
    "charges": [{"count": 1, "charge": "lion", "tincture": "gules"}],
}, "one charge on a plain field"

assert read_blazon_line("parted pale argent and gules; three mullets sable") == {
    "field": {"cut": "pale", "tinctures": ["argent", "gules"]},
    "charges": [{"count": 3, "charge": "mullet", "tincture": "sable"}],
}, "a parted field keeps its tinctures in written order"

assert read_blazon_line("parted fess sable and or; five crescents argent") == {
    "field": {"cut": "fess", "tinctures": ["sable", "or"]},
    "charges": [{"count": 5, "charge": "crescent", "tincture": "argent"}],
}, "fess division and the largest count"

assert read_blazon_line("vert; two roses argent; a bend or") == {
    "field": {"cut": "plain", "tinctures": ["vert"]},
    "charges": [
        {"count": 2, "charge": "rose", "tincture": "argent"},
        {"count": 1, "charge": "bend", "tincture": "or"},
    ],
}, "two charge clauses keep their order"

assert read_blazon_line("purpure; four bends or") == {
    "field": {"cut": "plain", "tinctures": ["purpure"]},
    "charges": [{"count": 4, "charge": "bend", "tincture": "or"}],
}, "the bare word is reported, not the plural"

assert rejects(""), "an empty line is refused"
assert rejects(17), "a non-string is refused"
assert rejects("beige"), "an unknown tincture is refused"
assert rejects("parted pale or and or"), "a parted field of one tincture is refused"
assert rejects("parted pale or"), "a truncated field clause is refused"
assert rejects("parted bend or and gules"), "an unknown division is refused"
assert rejects("azure; a lions gules"), "a plural word with a count of one is refused"
assert rejects("azure; two rose gules"), "a bare word with a count above one is refused"
assert rejects("azure; six lions or"), "an unknown count is refused"
assert rejects("azure; a dragon gules"), "an unknown charge word is refused"
assert rejects("azure; a lion"), "a two-word charge clause is refused"
assert rejects("azure; a lion gules; two lions or"), "a charge word named twice is refused"
assert rejects("azure; "), "an empty clause is refused"
print("ok")
