from solution import plural_noun

assert plural_noun("cat") == "cats", "default rule appends s"
assert plural_noun("bus") == "buses", "trailing s takes es"
assert plural_noun("box") == "boxes", "trailing x takes es"
assert plural_noun("buzz") == "buzzes", "trailing z takes es"
assert plural_noun("church") == "churches", "trailing ch takes es"
assert plural_noun("dish") == "dishes", "trailing sh takes es"
assert plural_noun("city") == "cities", "consonant plus y becomes ies"
assert plural_noun("day") == "days", "vowel plus y just appends s"
assert plural_noun("knife") == "knives", "trailing fe becomes ves"
assert plural_noun("leaf") == "leaves", "trailing f becomes ves"
assert plural_noun("child") == "children", "irregular child"
assert plural_noun("person") == "people", "irregular person"
assert plural_noun("mouse") == "mice", "irregular mouse"
assert plural_noun("sheep") == "sheep", "irregular sheep is unchanged"


def rejects(value):
    try:
        plural_noun(value)
    except ValueError:
        return True
    return False


assert rejects(""), "empty string is rejected"
assert rejects("Cat"), "uppercase is rejected"
assert rejects("two words"), "a space is rejected"
assert rejects("naïve"), "accented letters are rejected"
assert rejects(7), "a non-string is rejected"
print("ok")
