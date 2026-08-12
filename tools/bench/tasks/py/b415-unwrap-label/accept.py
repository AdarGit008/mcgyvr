from solution import unwrap_label

assert unwrap_label("[a]") == "a", "a matching pair is removed"
assert unwrap_label("[a") == "[a", "an unclosed bracket is left alone"
assert unwrap_label("a") == "a", "no brackets at all"
assert unwrap_label("[]") == "", "an empty pair"
assert unwrap_label("") == "", "an empty label"
assert unwrap_label("[ab]") == "ab", "a longer label"
print("ok")
