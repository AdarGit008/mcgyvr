from solution import crust_slice

assert crust_slice("notes.txt") == "notes", "the extension comes off"
assert crust_slice("archive.tar.gz") == "archive.tar", "only the final dot cuts"
assert crust_slice("README") == "README", "no dot, no cut"
assert crust_slice(".gitignore") == ".gitignore", "a hidden name is untouched"
assert crust_slice("trailing.") == "trailing", "a final dot still cuts"
assert crust_slice("") == "", "empty stays empty"
print("ok")
