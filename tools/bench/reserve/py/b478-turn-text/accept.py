from solution import turn_text

assert turn_text("abcd", "cdab") is True, "two characters moved to the back"
assert turn_text("abcd", "dabc") is True, "one character moved to the back"
assert turn_text("abcd", "abdc") is False, "the order inside is broken"
assert turn_text("abc", "abcd") is False, "texts of unlike length"
assert turn_text("aab", "aba") is True, "a repeated character still turns"
assert turn_text("", "") is True, "two texts holding nothing"
print("ok")
