from solution import plural_of

assert plural_of("bus") == "buses", "an s takes es"
assert plural_of("box") == "boxes", "an x takes es"
assert plural_of("match") == "matches", "a ch takes es"
assert plural_of("dish") == "dishes", "an sh takes es"
assert plural_of("city") == "cities", "a consonant then y gives ies"
assert plural_of("day") == "days", "a vowel then y just takes s"
assert plural_of("cat") == "cats", "everything else takes s"
print("ok")
