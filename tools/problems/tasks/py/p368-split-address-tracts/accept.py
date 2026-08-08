from solution import split_address_tracts


def rejects(root, wants):
    try:
        split_address_tracts(root, wants)
    except ValueError:
        return True
    return False


assert split_address_tracts("aaaaa/0", [30, 3, 100]) == {
    "refused": False,
    "tracts": ["baaaa/2", "bbaaa/4", "aaaaa/1"],
    "spare": 700,
}, "the roomiest want is served first and the rest fall in behind it"

assert split_address_tracts("aaaaa/3", [1, 4]) == {
    "refused": False,
    "tracts": ["aaaba/5", "aaaaa/4"],
    "spare": 11,
}, "a single address is pinned all five letters deep"

assert split_address_tracts("aaaaa/3", [4, 4, 4, 4]) == {
    "refused": False,
    "tracts": ["aaaaa/4", "aaaba/4", "aaaca/4", "aaada/4"],
    "spare": 0,
}, "wants of one length are laid down in the order they were listed"

assert split_address_tracts("baaaa/1", [200]) == {
    "refused": False,
    "tracts": ["baaaa/1"],
    "spare": 0,
}, "a want rounding up to the root's own span takes the root whole"

assert split_address_tracts("caaaa/1", [64, 64]) == {
    "refused": False,
    "tracts": ["caaaa/2", "cbaaa/2"],
    "spare": 128,
}, "a root away from the start still hands out runs in rising order"

assert split_address_tracts("baaaa/1", [300]) == {
    "refused": True,
    "tracts": [],
    "spare": 256,
}, "a want past the root's span is refused outright"

assert split_address_tracts("aaaaa/3", [1, 6]) == {
    "refused": True,
    "tracts": [],
    "spare": 16,
}, "a want that fills the root leaves nowhere for the small one"

assert split_address_tracts("aaaaa/2", [17, 17, 17, 17, 17]) == {
    "refused": True,
    "tracts": [],
    "spare": 64,
}, "five wants rounded to sixty-four cannot share a root of sixty-four"

assert rejects("aaaaa", [4]), "a root with no slash is rejected"
assert rejects("aaaaa/6", [4]), "a pinned count past five is rejected"
assert rejects("aaaab/0", [4]), "a letter past the pinned ones that is not a is rejected"
assert rejects("aaeaa/2", [4]), "a letter outside a to d is rejected"
assert rejects("aaaa/2", [4]), "an address of the wrong length is rejected"
assert rejects(9, [4]), "a root that is not a string is rejected"
assert rejects("aaaaa/0", []), "an empty want list is rejected"
assert rejects("aaaaa/0", [0]), "a want of zero is rejected"
assert rejects("aaaaa/0", [2.5]), "a fractional want is rejected"
assert rejects("aaaaa/0", "four"), "wants that are not a list are rejected"
print("ok")
