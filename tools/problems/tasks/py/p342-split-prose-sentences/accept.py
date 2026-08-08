from solution import split_prose_sentences


def rejects(*args):
    try:
        split_prose_sentences(*args)
    except ValueError:
        return True
    return False


assert split_prose_sentences("The rain fell. The road flooded.", []) == [
    "The rain fell.",
    "The road flooded.",
], "two plain sentences"
assert split_prose_sentences("Dr. Vance signed the form. She left.", ["Dr."]) == [
    "Dr. Vance signed the form.",
    "She left.",
], "a listed abbreviation cancels the candidate"
assert split_prose_sentences("Dr. Vance signed the form. She left.", []) == [
    "Dr.",
    "Vance signed the form.",
    "She left.",
], "an unlisted abbreviation breaks"
assert split_prose_sentences("The gauge read 3.5 bar. Nothing moved.", []) == [
    "The gauge read 3.5 bar.",
    "Nothing moved.",
], "a point with no space after it never breaks"
assert split_prose_sentences('He yelled "Stop! Now!" and sat down.', []) == [
    'He yelled "Stop! Now!" and sat down.'
], "an open quotation shields its stop marks"
assert split_prose_sentences(
    "Bring water (it may rain. bring more) now. Done.", []
) == ["Bring water (it may rain. bring more) now.", "Done."], (
    "brackets shield their stop marks"
)
assert split_prose_sentences("Really?! I doubt it.", []) == [
    "Really?!",
    "I doubt it.",
], "a run of stop marks is one candidate"
assert split_prose_sentences("Hold on... Then go.", []) == [
    "Hold on...",
    "Then go.",
], "three points end one sentence"
assert split_prose_sentences("We met e.g. on Tuesday. Fine.", ["e.g."]) == [
    "We met e.g. on Tuesday.",
    "Fine.",
], "an abbreviation carrying inner periods"
assert split_prose_sentences("", []) == [], "an empty passage"
assert split_prose_sentences("    ", []) == [], "a passage of spaces"
assert split_prose_sentences("Almost done", []) == [
    "Almost done"
], "a remainder with no stop mark"

assert rejects(42, []), "passage must be a string"
assert rejects("A tale.", "Dr."), "abbreviations must be a list"
assert rejects("A tale.", ["Dr"]), "an abbreviation must end in a period"
assert rejects("A tale.", ["a b."]), "an abbreviation may not hold a space"
assert rejects("Go) home.", []), "closing bracket with no opener"
assert rejects("Go (home.", []), "bracket left open"
assert rejects('He said "hi', []), "quotation left open"
print("ok")
