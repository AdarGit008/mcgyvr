from solution import section_numbers

assert section_numbers("A", 2) == ["1 A"], "one line gets 1"
assert section_numbers("A\nB\nC", 2) == ["1 A", "2 B", "3 C"], "flat lines count up"
assert section_numbers("A\n  B\n    C", 2) == [
    "1 A",
    "1.1 B",
    "1.1.1 C",
], "a straight descent"
assert section_numbers("A\n  B\n  C\nD\n  E", 2) == [
    "1 A",
    "1.1 B",
    "1.2 C",
    "2 D",
    "2.1 E",
], "counters restart under a new parent"
assert section_numbers("A\n  B\n    C\nD\n  E\n    F", 2) == [
    "1 A",
    "1.1 B",
    "1.1.1 C",
    "2 D",
    "2.1 E",
    "2.1.1 F",
], "restart holds two levels down"
assert section_numbers("A\n    B\n    C\nD\n    E", 4) == [
    "1 A",
    "1.1 B",
    "1.2 C",
    "2 D",
    "2.1 E",
], "a four-space unit behaves the same"


def rejects(*args):
    try:
        section_numbers(*args)
    except ValueError:
        return True
    return False


assert rejects("A", 0), "zero unit"
assert rejects("A", True), "boolean unit"
assert rejects("A\n   B", 2), "off-unit indentation"
assert rejects("A\n    B", 2), "two-step jump"
assert rejects("  A", 2), "opening line off margin"
print("ok")
