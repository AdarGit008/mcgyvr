from solution import audit_shield_contrast


def rejects(value):
    try:
        audit_shield_contrast(value)
    except ValueError:
        return True
    return False


KEEP = {
    "label": "keep",
    "field": ["azure"],
    "charges": [
        {"figure": "lion", "tincture": "or"},
        {"figure": "bend", "tincture": "gules"},
    ],
}
GATE = {
    "label": "gate",
    "field": ["argent"],
    "charges": [{"figure": "rose", "tincture": "gules"}],
}
TOWER = {
    "label": "tower",
    "field": ["or", "gules"],
    "charges": [
        {"figure": "mullet", "tincture": "argent"},
        {"figure": "crescent", "tincture": "or"},
    ],
}
WARD = {
    "label": "ward",
    "field": ["azure", "sable"],
    "charges": [{"figure": "lion", "tincture": "vert"}],
}
VANE = {
    "label": "vane",
    "field": ["or", "argent"],
    "charges": [
        {"figure": "bend", "tincture": "purpure"},
        {"figure": "rose", "tincture": "argent"},
    ],
}

assert audit_shield_contrast([KEEP]) == [
    {"label": "keep", "unsound": ["bend"]}
], "colour on a colour field is unsound"
assert audit_shield_contrast([GATE]) == [], "a wholly sound shield is left out"
assert audit_shield_contrast([TOWER]) == [
    {"label": "tower", "unsound": ["crescent"]}
], "a tincture shared with a half is unsound even where the classes differ"
assert audit_shield_contrast([WARD]) == [
    {"label": "ward", "unsound": ["lion"]}
], "two colour halves contrast with no colour figure"
assert audit_shield_contrast([VANE]) == [
    {"label": "vane", "unsound": ["rose"]}
], "two metal halves still admit a colour figure"
assert audit_shield_contrast([GATE, KEEP, TOWER]) == [
    {"label": "keep", "unsound": ["bend"]},
    {"label": "tower", "unsound": ["crescent"]},
], "the surviving shields keep the order they arrived in"
assert (
    audit_shield_contrast([{"label": "bare", "field": ["vert"], "charges": []}]) == []
), "a shield bearing nothing reports nothing"
assert audit_shield_contrast([]) == [], "an empty roll of shields is empty"

assert rejects(5), "a non-list is refused"
assert rejects([{"label": "", "field": ["vert"], "charges": []}]), "an empty label is refused"
assert rejects([KEEP, dict(KEEP)]), "a repeated label is refused"
assert rejects([{"label": "void", "field": [], "charges": []}]), "a field of no tinctures is refused"
assert rejects(
    [{"label": "third", "field": ["or", "vert", "sable"], "charges": []}]
), "a field of three tinctures is refused"
assert rejects(
    [{"label": "odd", "field": ["beige"], "charges": []}]
), "an unknown field tincture is refused"
assert rejects(
    [
        {
            "label": "odd",
            "field": ["vert"],
            "charges": [{"figure": "lion", "tincture": "puce"}],
        }
    ]
), "an unknown figure tincture is refused"
assert rejects(
    [
        {
            "label": "twice",
            "field": ["vert"],
            "charges": [
                {"figure": "lion", "tincture": "or"},
                {"figure": "lion", "tincture": "argent"},
            ],
        }
    ]
), "the same figure borne twice is refused"
print("ok")
