from solution import unspool_text

assert unspool_text("abc") == "abc", "text with no pointer is itself"
assert unspool_text("") == "", "the empty spool produces nothing"
assert unspool_text("ab<2,2>") == "abab", "a pointer that does not overlap"
assert unspool_text("ab<1,4>") == "abbbbb", "a haul larger than its reach"
assert (
    unspool_text("xyz<3,3><6,6>") == "xyzxyzxyzxyz"
), "a pointer reading what an earlier pointer wrote"
assert unspool_text("ab<<c") == "ab<c", "a doubled sign is one literal sign"
assert unspool_text("a>b") == "a>b", "a lone greater-than sign is literal"
assert unspool_text("<<") == "<", "a spool that is only the escape"
assert unspool_text("ha<2,10>") == "hahahahahaha", "a long overlapping haul"
assert unspool_text("abcd<4,2>ef") == "abcdabef", "text resumes after a pointer"
assert unspool_text("ab<2,2>>") == "abab>", "a closer followed by a literal"
assert unspool_text("ab<2,1>") == "aba", "a haul of one"


def rejects(value):
    try:
        unspool_text(value)
    except ValueError:
        return True
    return False


assert rejects("<1,2>"), "a pointer with nothing behind it"
assert rejects("ab<3,1>"), "a reach past the start"
assert rejects("ab<2>"), "a missing comma is rejected"
assert rejects("ab<2,2"), "a missing closer is rejected"
assert rejects("ab<0,2>"), "a zero reach is rejected"
assert rejects("ab<2,0>"), "a zero haul is rejected"
assert rejects("ab<02,2>"), "a padded reach is rejected"
assert rejects("ab<x,2>"), "a non-numeric field is rejected"
assert rejects("ab<"), "a dangling sign is rejected"
assert rejects(3), "a non-string spool is rejected"
print("ok")
