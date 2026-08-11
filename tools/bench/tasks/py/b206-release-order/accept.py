from solution import order_release_tags

assert order_release_tags(["v1.10.0", "v1.9.3"]) == ["v1.9.3", "v1.10.0"], "version fields compare as numbers"
assert order_release_tags(["v2.0.0", "v2.0.0-rc1"]) == ["v2.0.0-rc1", "v2.0.0"], "a preview comes before its release"
assert order_release_tags(["v3.1.0-rc10", "v3.1.0-rc2"]) == ["v3.1.0-rc2", "v3.1.0-rc10"], "preview numbers compare as numbers"
assert order_release_tags(["v4.0.0-beta1", "v4.0.0-alpha9"]) == ["v4.0.0-alpha9", "v4.0.0-beta1"], "preview words compare alphabetically"
assert order_release_tags(["v0.2.1", "v0.10.0", "v0.2.10"]) == ["v0.2.1", "v0.2.10", "v0.10.0"], "minor outranks patch"
given = ["v2.0.0", "v1.0.0"]
assert order_release_tags(given) == ["v1.0.0", "v2.0.0"], "the ordered tags come back"
assert given == ["v2.0.0", "v1.0.0"], "the given list is left untouched"
assert order_release_tags([]) == [], "an empty list stays empty"
print("ok")
