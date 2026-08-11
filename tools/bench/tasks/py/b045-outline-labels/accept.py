from solution import number_sections, section_count

DOC = [
    {"heading": "Intro", "children": [
        {"heading": "Scope", "children": []},
        {"heading": "Terms", "children": [{"heading": "Symbols", "children": []}]},
    ]},
    {"heading": "Methods", "children": []},
]
assert number_sections([]) == [], "an empty outline has no labels"
assert number_sections([{"heading": "Solo", "children": []}]) == ["1 Solo"], "a lone section is labelled 1"
assert number_sections(DOC) == [
    "1 Intro",
    "1.1 Scope",
    "1.2 Terms",
    "1.2.1 Symbols",
    "2 Methods",
], "nested sections take dotted labels in document order"
assert section_count(DOC) == 5, "every depth counts toward the section count"


def rejects(value):
    try:
        number_sections(value)
    except ValueError:
        return True
    return False


assert rejects("outline"), "a non-list argument is rejected"
assert rejects([42]), "a non-mapping section is rejected"
assert rejects([{"heading": "", "children": []}]), "an empty heading is rejected"
assert rejects([{"heading": "A"}]), "a missing children list is rejected"
assert rejects([{"heading": "A", "children": [{"heading": 7, "children": []}]}]), "a bad deep heading is rejected"
print("ok")
