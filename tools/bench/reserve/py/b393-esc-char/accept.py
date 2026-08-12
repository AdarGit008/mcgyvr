from solution import esc_char

assert esc_char("a,b", ",") == "a^,b", "the marked character is escaped"
assert esc_char("ab", ",") == "ab", "nothing to escape"
assert esc_char("", ",") == "", "an empty text"
assert esc_char("a^b", ",") == "a^^b", "a caret already there is escaped"
assert esc_char(",,", ",") == "^,^,", "two in a row"
assert esc_char("a", "a") == "^a", "the whole text is escaped"
print("ok")
