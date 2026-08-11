from solution import flag_list

assert flag_list("-a -b") == ["a", "b"], "two flags, dashes stripped"
assert flag_list("-a file") == ["a"], "a plain word is not a flag"
assert flag_list("file") == [], "no flags on the line"
assert flag_list("") == [], "an empty line"
assert flag_list("-x") == ["x"], "a single flag"
assert flag_list("-a -a") == ["a", "a"], "a repeated flag is kept twice"
print("ok")
