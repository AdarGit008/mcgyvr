from solution import decode_escaped_note

assert decode_escaped_note("meet the courier at nine") == "meet the courier at nine", "a note without escapes is unchanged"
assert decode_escaped_note("50=25 off, tea =26 buns") == "50% off, tea & buns", "escapes stand for their characters"
assert decode_escaped_note("the crate held car=\nrots") == "the crate held carrots", "a trailing equals folds the next line on"
assert decode_escaped_note("first row   \nsecond row") == "first row\nsecond row", "trailing blanks vanish and the break stays"
assert decode_escaped_note("keep me=20\nnext") == "keep me \nnext", "an escaped space outlives the trimming pass"
assert decode_escaped_note("") == "", "an empty note decodes to nothing"


def rejects(value):
    try:
        decode_escaped_note(value)
    except Exception:
        return True
    return False


assert rejects("=G1 crates"), "an escape that is not two hex digits is rejected"
print("ok")
