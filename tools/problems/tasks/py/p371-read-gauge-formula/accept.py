from solution import read_gauge_formula

BOOK = {
    "span": "12 flit",
    "tick": "3 mor",
    "pace": "4 flit*mor^-1",
    "drift": "5",
    "odd": "7 flit",
    "back": "-6 flit",
    "nil": "0",
    "mix": "2 zed*ark^2",
}


def bent(patch):
    book = dict(BOOK)
    book.update(patch)
    return book


def rejects(table, formula):
    try:
        read_gauge_formula(table, formula)
    except ValueError:
        return True
    return False


assert read_gauge_formula(BOOK, "span") == "12 flit", "a lone label reads back"
assert (
    read_gauge_formula(BOOK, "span/tick") == "4 flit*mor^-1"
), "dividing turns the divisor's exponent negative"
assert (
    read_gauge_formula(BOOK, "pace*tick") == "12 flit"
), "a name whose exponent reaches zero disappears"
assert read_gauge_formula(BOOK, "span+odd") == "19 flit", "like quantities add"
assert (
    read_gauge_formula(BOOK, "drift*drift") == "25"
), "a quantity with no units is written bare"
assert (
    read_gauge_formula(BOOK, "mix") == "2 ark^2*zed"
), "names come out in rising alphabetical order, exponent one written bare"
assert (
    read_gauge_formula(BOOK, "span/tick+pace") == "8 flit*mor^-1"
), "products are worked out before the plus signs join them"
assert (
    read_gauge_formula(BOOK, "span+back") == "6 flit"
), "a negative number in the table subtracts"
assert (
    read_gauge_formula(BOOK, "span+back+back") == "0 flit"
), "a result of nothing still carries its units"
assert (
    read_gauge_formula(BOOK, "pace*pace") == "16 flit^2*mor^-2"
), "squaring doubles every exponent"

assert rejects(BOOK, "span/drift"), "a division that does not come out whole is rejected"
assert rejects(BOOK, "span/nil"), "dividing by nothing is rejected"
assert rejects(BOOK, "span+tick"), "adding unlike quantities is rejected"
assert rejects(BOOK, "span*"), "a trailing operator is rejected"
assert rejects(BOOK, "*span"), "a leading operator is rejected"
assert rejects(BOOK, "span**tick"), "a doubled operator is rejected"
assert rejects(BOOK, "span+"), "a trailing plus is rejected"
assert rejects(BOOK, ""), "an empty formula is rejected"
assert rejects(BOOK, "ghost"), "an unknown label is rejected"
assert rejects(BOOK, "Span"), "a label outside the small letters is rejected"
assert rejects(BOOK, 7), "a formula that is not a string is rejected"
assert rejects(
    bent({"bad": "12 flit^0"}), "span"
), "a zero exponent anywhere in the table is rejected"
assert rejects(
    bent({"bad": "12 flit*flit"}), "span"
), "a unit name written twice in one quantity is rejected"
assert rejects(
    bent({"bad": "1.5 flit"}), "span"
), "a quantity that is not a whole number is rejected"
assert rejects(
    bent({"bad": "12 flit^+2"}), "span"
), "an exponent carrying a plus sign is rejected"
assert rejects(
    {"Bad": "12 flit"}, "span"
), "a table label outside the small letters is rejected"
assert rejects("book", "span"), "a table that is not a mapping is rejected"
print("ok")
