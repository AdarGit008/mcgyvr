from solution import collapse_blocks


def berth(value):
    fields = []
    rest = value
    for _ in range(4):
        fields.insert(0, rest % 8)
        rest //= 8
    return ".".join(str(field) for field in fields)


assert collapse_blocks([]) == [], "no berths, no slabs"
assert collapse_blocks(["3.1.4.2"]) == ["3.1.4.2/4"], "one berth is a full pin"
assert collapse_blocks(["1.1.1.1", "1.1.1.1"]) == [
    "1.1.1.1/4"
], "a repeated berth counts once"
assert collapse_blocks(["7.0.0.0", "0.0.0.1"]) == [
    "0.0.0.1/4",
    "7.0.0.0/4",
], "slabs come out lowest first"

eight = ["1.2.3." + str(last) for last in range(8)]
assert collapse_blocks(eight) == ["1.2.3.0/3"], "eight siblings fold to one"
assert collapse_blocks(eight[:7]) == [
    one + "/4" for one in eight[:7]
], "seven siblings stay written out"
assert collapse_blocks(eight + ["5.5.5.5"]) == [
    "1.2.3.0/3",
    "5.5.5.5/4",
], "a fold and a lone berth together"

sixty_four = [
    "0.0." + str(third) + "." + str(last) for third in range(8) for last in range(8)
]
assert collapse_blocks(sixty_four) == ["0.0.0.0/2"], "folding runs twice in a row"
assert collapse_blocks(sixty_four[1:]) == [
    "0.0.0.1/4",
    "0.0.0.2/4",
    "0.0.0.3/4",
    "0.0.0.4/4",
    "0.0.0.5/4",
    "0.0.0.6/4",
    "0.0.0.7/4",
    "0.0.1.0/3",
    "0.0.2.0/3",
    "0.0.3.0/3",
    "0.0.4.0/3",
    "0.0.5.0/3",
    "0.0.6.0/3",
    "0.0.7.0/3",
], "one berth missing stops only its own group folding"

everything = [berth(value) for value in range(4096)]
assert collapse_blocks(everything) == ["0.0.0.0/0"], "the whole space folds"
assert collapse_blocks(everything[:512]) == [
    "0.0.0.0/1"
], "one eighth of the space folds to a single pin"


def rejects(value):
    try:
        collapse_blocks(value)
    except ValueError:
        return True
    return False


assert rejects(["1.2.3"]), "three fields are rejected"
assert rejects(["1.2.3.4.5"]), "five fields are rejected"
assert rejects(["1.2.3.8"]), "a field of eight is rejected"
assert rejects(["1.2.3.a"]), "a letter field is rejected"
assert rejects(["1.2..3"]), "an empty field is rejected"
assert rejects(["01.2.3.4"]), "a padded field is rejected"
assert rejects("1.2.3.4"), "a bare string is rejected"
assert rejects([17]), "a non-string element is rejected"
print("ok")
