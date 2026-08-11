from solution import crumb_split, crumb_join

assert crumb_split("/docs//api/") == ["docs", "api"], "empties dropped"
assert crumb_split("docs") == ["docs"], "a single segment"
assert crumb_split("") == [], "an empty trail"
assert crumb_split("///") == [], "slashes only"
assert crumb_join(["docs", "api"]) == "docs/api", "one slash between"
assert crumb_join(["docs", "", "api"]) == "docs/api", "an empty part is dropped"
assert crumb_join([]) == "", "nothing joins to nothing"
print("ok")
