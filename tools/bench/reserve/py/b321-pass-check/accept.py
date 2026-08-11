from solution import pass_check

assert pass_check("abcd1234") is True, "long enough with both"
assert pass_check("abcdefgh") is False, "no digit"
assert pass_check("12345678") is False, "no letter"
assert pass_check("ab12") is False, "too short"
assert pass_check("") is False, "an empty passphrase"
assert pass_check("Passw0rdd") is True, "capitals count as letters"
print("ok")
