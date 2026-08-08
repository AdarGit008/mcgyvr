from solution import mask_sensitive


def rejects(note):
    try:
        mask_sensitive(note)
    except ValueError:
        return True
    return False


assert mask_sensitive("") == {"text": "", "badges": 0, "vaults": 0}, (
    "an empty note carries nothing"
)
assert mask_sensitive("ticket AB-1234 filed") == {
    "text": "ticket AB-#### filed",
    "badges": 1,
    "vaults": 0,
}, "a badge keeps its letters, its hyphen and its length"
assert mask_sensitive("WXYZ-12345678.") == {
    "text": "WXYZ-########.",
    "badges": 1,
    "vaults": 0,
}, "four letters and eight digits are still a badge"
assert mask_sensitive("ABCDE-1234 and A-1234 and AB-123 and AB-123456789") == {
    "text": "ABCDE-1234 and A-1234 and AB-123 and AB-123456789",
    "badges": 0,
    "vaults": 0,
}, "one letter or digit outside the range makes it no badge at all"
assert mask_sensitive("XY-1234AB-5678") == {
    "text": "XY-####AB-####",
    "badges": 2,
    "vaults": 0,
}, "a badge may begin right where the one before it ended"
assert mask_sensitive("see vk=abc123 now") == {
    "text": "see [vault] now",
    "badges": 0,
    "vaults": 1,
}, "a vault key goes entirely, token and all"
assert mask_sensitive("vk=abcde vk=abcdefghijk myvk=abc123") == {
    "text": "vk=abcde vk=abcdefghijk myvk=abc123",
    "badges": 0,
    "vaults": 0,
}, "too short, too long, and glued to a word: none of them is a vault key"
assert mask_sensitive("vk=abc123X") == {
    "text": "[vault]X",
    "badges": 0,
    "vaults": 1,
}, "a capital ends the stretch, so the six before it stand"
assert mask_sensitive("QQ-4444/ZZZ-55555 vk=zz99aa!") == {
    "text": "QQ-####/ZZZ-##### [vault]!",
    "badges": 2,
    "vaults": 1,
}, "both shapes in one note are counted apart"
assert mask_sensitive("hash # and vault already") == {
    "text": "hash # and vault already",
    "badges": 0,
    "vaults": 0,
}, "a note with neither shape comes back untouched"

assert rejects(1234), "a number is not a note"
assert rejects(None), "nothing is not a note"
print("ok")
