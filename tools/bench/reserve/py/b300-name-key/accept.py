from solution import sort_key

assert sort_key("Ada Lovelace") == "lovelace ada", "surname leads"
assert sort_key("Grace Hopper") == "hopper grace", "another pair"
assert sort_key("prince") == "prince", "one word stands alone"
assert sort_key("Prince") == "prince", "and is lowered"
assert sort_key("") == "", "an empty name"
assert sort_key("Ann Van Dyke") == "van dyke ann", "only the first space cuts"
print("ok")
