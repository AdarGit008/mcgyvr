from solution import rank_stemmed_terms

plain = {"stops": [], "endings": []}

assert rank_stemmed_terms(
    "Cats ran; the cat runs and a cat rested. Resting cats rest!",
    {"stops": ["the", "a", "run"], "endings": [["ing", 3], ["ed", 3], ["s", 3]]},
) == [
    ("cat", 4),
    ("rest", 3),
    ("and", 1),
    ("ran", 1),
], "trimming happens first and the stop list is weighed against the trimmed word"
assert rank_stemmed_terms("is as gas cars", {"stops": [], "endings": [["s", 3]]}) == [
    ("as", 1),
    ("car", 1),
    ("gas", 1),
    ("is", 1),
], "a floor blocks the trim and equal counts sort alphabetically"
assert rank_stemmed_terms(
    "Boxes boxes box", {"stops": [], "endings": [["es", 4], ["s", 2]]}
) == [
    ("boxe", 2),
    ("box", 1),
], "a pair that breaks its floor is passed over and a later pair fires"
assert rank_stemmed_terms("", plain) == [], "an empty passage counts nothing"
assert rank_stemmed_terms("42 -- 7", plain) == [], "a passage with no letters counts nothing"
assert (
    rank_stemmed_terms("The the a A", {"stops": ["the", "a"], "endings": []}) == []
), "a passage of nothing but stop words counts nothing"
assert rank_stemmed_terms("Dogs dogs DOG", plain) == [
    ("dogs", 2),
    ("dog", 1),
], "with no endings the folded words are counted as they stand"
assert rank_stemmed_terms("e-mail e mail 42 mail3", plain) == [
    ("mail", 3),
    ("e", 2),
], "digits and punctuation only separate words"
assert rank_stemmed_terms("runs run running", {"stops": ["run"], "endings": [["s", 3]]}) == [
    ("running", 1)
], "an untrimmed spelling on the stop list is dropped only once it matches after trimming"
assert rank_stemmed_terms(
    "walked walking walks walk",
    {"stops": [], "endings": [["ing", 4], ["ed", 4], ["s", 4]]},
) == [("walk", 4)], "several endings fold to one term"


def rejects(passage, rules):
    try:
        rank_stemmed_terms(passage, rules)
    except ValueError:
        return True
    return False


assert rejects(5, plain), "a non-string passage is rejected"
assert rejects("cat", None), "a missing rules mapping is rejected"
assert rejects("cat", [[], []]), "rules given as a list are rejected"
assert rejects("cat", {"stops": [], "endings": "s"}), "endings that are not a list are rejected"
assert rejects("cat", {"stops": "the", "endings": []}), "stops that are not a list are rejected"
assert rejects("cat", {"stops": ["The"], "endings": []}), "a capitalised stop word is rejected"
assert rejects("cat", {"stops": [""], "endings": []}), "an empty stop word is rejected"
assert rejects(
    "cat", {"stops": [], "endings": [["s"]]}
), "an endings entry that is not a pair is rejected"
assert rejects("cat", {"stops": [], "endings": [["S", 2]]}), "a capitalised tail is rejected"
assert rejects("cat", {"stops": [], "endings": [["s", 0]]}), "a floor of zero is rejected"
assert rejects("cat", {"stops": [], "endings": [["s", 1.5]]}), "a fractional floor is rejected"
print("ok")
