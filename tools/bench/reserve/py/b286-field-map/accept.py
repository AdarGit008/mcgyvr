from solution import field_map

assert field_map(["a=1", "b=2"]) == {"a": "1", "b": "2"}, "two settings"
assert field_map(["a=1", "a=2"]) == {"a": "2"}, "the later one wins"
assert field_map(["plain"]) == {}, "no equals sign, skipped"
assert field_map([]) == {}, "nothing to read"
assert field_map(["url=http://x?y=z"]) == {
    "url": "http://x?y=z"
}, "only the first equals separates"
assert field_map(["a="]) == {"a": ""}, "an empty value is still a value"
print("ok")
