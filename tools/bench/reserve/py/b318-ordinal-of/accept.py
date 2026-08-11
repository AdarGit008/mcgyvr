from solution import ordinal_of

assert ordinal_of(1) == "1st", "one takes st"
assert ordinal_of(2) == "2nd", "two takes nd"
assert ordinal_of(3) == "3rd", "three takes rd"
assert ordinal_of(4) == "4th", "everything else takes th"
assert ordinal_of(11) == "11th", "the teens are the exception"
assert ordinal_of(12) == "12th", "and so is twelve"
assert ordinal_of(13) == "13th", "and thirteen"
assert ordinal_of(21) == "21st", "past the teens the rule returns"
print("ok")
