from solution import render_postal_lines

FULL = {
    "who": "Ilva Renn",
    "house": "12b",
    "street": "Marl  Row",
    "ward": "Upper Fen",
    "town": "hesketh",
    "code": "vk-4471",
}

assert render_postal_lines(FULL, "vela") == [
    "Ilva Renn",
    "12b Marl Row",
    "vk-4471 HESKETH",
], "vela writes three lines and shouts the town alone"
assert render_postal_lines(FULL, "korrin") == [
    "ILVA RENN",
    "Marl Row 12b",
    "hesketh",
    "VK-4471",
], "korrin puts the street before the house and shouts who and code"
assert render_postal_lines(FULL, "mebis") == [
    "ILVA RENN",
    "UPPER FEN",
    "MARL ROW 12B",
    "HESKETH VK-4471",
], "mebis writes the ward and shouts everything"

assert render_postal_lines(
    {
        "who": "  Orin  Kade ",
        "house": " 4 ",
        "street": "Low Gate",
        "town": "  arden",
        "code": "q7",
    },
    "vela",
) == ["Orin Kade", "4 Low Gate", "q7 ARDEN"], "values are trimmed and inner blanks squeezed"

assert render_postal_lines({**FULL, "ward": "  ", "note": "kept back"}, "korrin") == [
    "ILVA RENN",
    "Marl Row 12b",
    "hesketh",
    "VK-4471",
], "a value korrin never writes is ignored even when blank, and so are strangers"

assert render_postal_lines(
    {"who": "a", "house": "b", "street": "c", "ward": "d", "town": "e", "code": "f"},
    "mebis",
) == ["A", "D", "C B", "E F"], "single letters shout the same way"


def rejects(entry, region):
    try:
        render_postal_lines(entry, region)
    except ValueError:
        return True
    return False


assert rejects("not a record", "vela"), "entry must be a record"
assert rejects([FULL], "vela"), "a list is not a record"
assert rejects(FULL, "nowhere"), "an unknown region is rejected"
assert rejects(FULL, ""), "an empty region is rejected"
assert rejects({**FULL, "ward": "   "}, "mebis"), "mebis needs the ward"
assert rejects(
    {"who": "a", "house": "b", "street": "c", "town": "e"}, "vela"
), "vela needs the code"
assert rejects({**FULL, "house": 12}, "vela"), "a value that is not a string is missing"
assert rejects({**FULL, "town": ""}, "korrin"), "an empty town is missing"
print("ok")
