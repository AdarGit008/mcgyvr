from solution import recode_answer_sheet

STEPS = [
    {"label": "GOOD", "wanted": ["good", "great", "lovely"], "barred": ["not "], "least": 2},
    {"label": "SLOW", "wanted": ["slow", "late", "wait"], "barred": [], "least": 1},
]

SOUND = {
    "steps": [{"label": "A", "wanted": ["ok"], "barred": [], "least": 1}],
    "entries": [{"id": "e1", "text": "ok"}],
}


def bent(patch):
    sheet = dict(SOUND)
    sheet.update(patch)
    return sheet


def rejects(sheet):
    try:
        recode_answer_sheet(sheet)
    except ValueError:
        return True
    return False


assert recode_answer_sheet(
    {
        "steps": STEPS,
        "entries": [
            {"id": "e1", "text": "Good and great service"},
            {"id": "e2", "text": "good but not great"},
            {"id": "e3", "text": "very slow"},
            {"id": "e4", "text": "Good only"},
            {"id": "e5", "text": "  LATE\n\n  again  "},
        ],
    }
) == {
    "coded": [
        {"id": "e1", "label": "GOOD"},
        {"id": "e3", "label": "SLOW"},
        {"id": "e5", "label": "SLOW"},
    ],
    "loose": ["e2", "e4"],
    "unused": [],
}, "the whole sheet, thresholds and bars and folding together"

assert recode_answer_sheet(
    {
        "steps": [{"label": "GOOD", "wanted": ["good", "great"], "barred": [], "least": 2}],
        "entries": [{"id": "a", "text": "good"}, {"id": "b", "text": "good and great"}],
    }
) == {
    "coded": [{"id": "b", "label": "GOOD"}],
    "loose": ["a"],
    "unused": [],
}, "one fragment short of least is not enough"

assert recode_answer_sheet(
    {
        "steps": [
            {"label": "X", "wanted": ["cost"], "barred": ["free"], "least": 1},
            {"label": "Y", "wanted": ["cost"], "barred": [], "least": 1},
        ],
        "entries": [{"id": "a", "text": "cost free"}],
    }
) == {
    "coded": [{"id": "a", "label": "Y"}],
    "loose": [],
    "unused": ["X"],
}, "a barred fragment sends the entry on to the next step"

assert recode_answer_sheet(
    {
        "steps": [{"label": "BUS", "wanted": ["slow bus"], "barred": [], "least": 1}],
        "entries": [{"id": "a", "text": "the slow\n   bus"}],
    }
) == {
    "coded": [{"id": "a", "label": "BUS"}],
    "loose": [],
    "unused": [],
}, "whitespace inside the text squeezes down before the fragment is sought"

assert recode_answer_sheet(
    {
        "steps": [
            {"label": "FIRST", "wanted": ["rain"], "barred": [], "least": 1},
            {"label": "SECOND", "wanted": ["rain"], "barred": [], "least": 1},
        ],
        "entries": [{"id": "a", "text": "rain"}],
    }
) == {
    "coded": [{"id": "a", "label": "FIRST"}],
    "loose": [],
    "unused": ["SECOND"],
}, "the earlier step takes it when both would"

assert recode_answer_sheet({"steps": STEPS, "entries": []}) == {
    "coded": [],
    "loose": [],
    "unused": ["GOOD", "SLOW"],
}, "no entries leaves every step unused"

assert recode_answer_sheet(
    {
        "steps": [{"label": "A", "wanted": ["x"], "barred": [], "least": 1}],
        "entries": [{"id": "a", "text": "   "}, {"id": "b", "text": ""}],
    }
) == {
    "coded": [],
    "loose": ["a", "b"],
    "unused": ["A"],
}, "text that folds away to nothing is loose"

assert recode_answer_sheet(
    {
        "steps": [{"label": "A", "wanted": ["late"], "barred": ["not late"], "least": 1}],
        "entries": [{"id": "a", "text": "NOT   LATE"}],
    }
) == {
    "coded": [],
    "loose": ["a"],
    "unused": ["A"],
}, "a bar is sought in the folded text just as a wanted fragment is"

assert rejects(["steps"]), "a sheet that is not a mapping is rejected"
assert rejects(bent({"steps": []})), "an empty step list is rejected"
assert rejects(bent({"steps": "A"})), "steps that are not a list are rejected"
assert rejects(bent({"entries": "e"})), "entries that are not a list are rejected"
assert rejects(
    bent({"steps": [{"label": "", "wanted": ["ok"], "barred": [], "least": 1}]})
), "an empty label is rejected"
assert rejects(
    bent(
        {
            "steps": [
                {"label": "A", "wanted": ["ok"], "barred": [], "least": 1},
                {"label": "A", "wanted": ["no"], "barred": [], "least": 1},
            ]
        }
    )
), "two steps sharing a label are rejected"
assert rejects(
    bent({"steps": [{"label": "A", "wanted": [], "barred": [], "least": 1}]})
), "a step wanting nothing is rejected"
assert rejects(
    bent({"steps": [{"label": "A", "wanted": ["Ok"], "barred": [], "least": 1}]})
), "a fragment carrying a capital is rejected"
assert rejects(
    bent({"steps": [{"label": "A", "wanted": ["ok", "ok"], "barred": [], "least": 1}]})
), "a repeated fragment is rejected"
assert rejects(
    bent({"steps": [{"label": "A", "wanted": ["ok"], "barred": "no", "least": 1}]})
), "barred that is not a list is rejected"
assert rejects(
    bent({"steps": [{"label": "A", "wanted": ["ok"], "barred": [], "least": 2}]})
), "least beyond the wanted list is rejected"
assert rejects(
    bent({"steps": [{"label": "A", "wanted": ["ok"], "barred": [], "least": 0}]})
), "least below one is rejected"
assert rejects(bent({"entries": [{"id": "", "text": "ok"}]})), "an empty id is rejected"
assert rejects(
    bent({"entries": [{"id": "a", "text": "ok"}, {"id": "a", "text": "ok"}]})
), "two entries sharing an id are rejected"
assert rejects(bent({"entries": [{"id": "a", "text": 5}]})), "text that is not a string is rejected"

print("ok")
