from solution import initials_of

assert initials_of("ada lovelace") == "A.L.", "two words, two initials"
assert initials_of("Grace  Brewster   Hopper") == "G.B.H.", "wide gaps are one break"
assert initials_of("prince") == "P.", "one word still closes with a dot"
assert initials_of("") == "", "no name, no initials"
assert initials_of("   ") == "", "spaces alone hold no words"
assert initials_of("  jo  ann  ") == "J.A.", "the ends are ignored"
print("ok")
