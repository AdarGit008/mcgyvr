from solution import title_line

assert title_line("the moon and the stars", ["and", "the"]) == "The Moon and the Stars", "quiet words stay quiet in the middle"
assert title_line("a NASA report", ["a"]) == "A NASA Report", "capitals throughout survive"
assert title_line("don't stop", []) == "Don't Stop", "a one letter tail stays small"
assert title_line("o'brien of x-ray", ["of"]) == "O'Brien of X-Ray", "longer tails and hyphen pieces are raised"
assert title_line("and", ["and"]) == "And", "a lone token is both front and back"
assert title_line("war of the WORLDS", ["of", "the"]) == "War of the WORLDS", "an untouched token can close the heading"
assert title_line("mixED cASe", []) == "Mixed Case", "stray capitals are lowered"
assert title_line("route 66 north", []) == "Route 66 North", "a digit token is copied through"
assert title_line("the end of the", ["of", "the"]) == "The End of The", "the closing token is never quiet"
assert title_line("rock'n'roll", []) == "Rock'N'Roll", "every inner piece is raised"
assert title_line("HR-2 draft", ["of"]) == "Hr-2 Draft", "a hyphen keeps a token off the untouched path"


def rejects(text, quiet):
    try:
        title_line(text, quiet)
    except ValueError:
        return True
    return False


assert rejects("", []), "an empty heading is rejected"
assert rejects(" lead", []), "a leading space is rejected"
assert rejects("trail ", []), "a trailing space is rejected"
assert rejects("two  gaps", []), "a doubled space is rejected"
assert rejects("bad.token", []), "a stray character is rejected"
assert rejects("-lead", []), "a token opening with a hyphen is rejected"
assert rejects("trail'", []), "a token closing with an apostrophe is rejected"
assert rejects(7, []), "a non-string heading is rejected"
assert rejects("ok", "and"), "a quiet list that is not a list is rejected"
assert rejects("ok", ["The"]), "a quiet entry with a capital is rejected"
assert rejects("ok", [5]), "a non-string quiet entry is rejected"
print("ok")
