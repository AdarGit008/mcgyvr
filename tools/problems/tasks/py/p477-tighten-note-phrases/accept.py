from solution import tighten_note_phrases

BOOK = {
    "as soon": "asn",
    "as soon as possible": "asap",
    "class": "cls",
    "north road": "nrd",
    "nrd": "nr",
}

assert (
    tighten_note_phrases("as soon as possible", BOOK) == "asap"
), "the longest phrase wins over one the book happens to list first"
assert (
    tighten_note_phrases("as soon after", BOOK) == "asn after"
), "a shorter phrase still matches where the longer one does not"
assert (
    tighten_note_phrases("classroom", BOOK) == "classroom"
), "a phrase buried at the front of a longer word is not a match"
assert (
    tighten_note_phrases("classy", BOOK) == "classy"
), "a letter straight after the run blocks the match"
assert (
    tighten_note_phrases("the class met", BOOK) == "the cls met"
), "a phrase standing as its own word is written short"
assert (
    tighten_note_phrases("As soon as possible, please.", BOOK) == "Asap, please."
), "a run opening with a capital raises the contraction"
assert (
    tighten_note_phrases("North Road runs east", BOOK) == "Nrd runs east"
), "a two-word phrase matches blind to case"
assert (
    tighten_note_phrases("nrd", BOOK) == "nr"
), "a one-word phrase is written short like any other"
assert (
    tighten_note_phrases("as  soon", BOOK) == "as  soon"
), "a doubled space parts the words too widely to match"
assert tighten_note_phrases("", BOOK) == "", "empty text stays empty"
assert (
    tighten_note_phrases("nothing in the book here", BOOK)
    == "nothing in the book here"
), "text the book never mentions comes back untouched"
assert (
    tighten_note_phrases("Class of 99", BOOK) == "Cls of 99"
), "digits after a space do not join the word before them"


def rejects(text, book):
    try:
        tighten_note_phrases(text, book)
    except ValueError:
        return True
    return False


assert rejects(7, BOOK), "a text that is not a string is rejected"
assert rejects("class", ["class"]), "a book that is not a mapping is rejected"
assert rejects("class", {"As Soon": "asn"}), "a key holding capitals is rejected"
assert rejects("class", {"as  soon": "asn"}), "a key with a doubled space is rejected"
assert rejects("class", {"as-soon": "asn"}), "a key holding a hyphen is rejected"
assert rejects("class", {"as soon": ""}), "an empty contraction is rejected"
assert rejects("class", {"as soon": "ASN"}), "a contraction in capitals is rejected"
assert rejects("class", {"as soon": 5}), "a contraction that is not a string is rejected"
print("ok")
