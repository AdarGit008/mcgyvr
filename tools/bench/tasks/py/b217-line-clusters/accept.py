from solution import line_clusters

assert line_clusters(["depot", "market", "pier"], [("depot", "market"), ("market", "pier")]) == [["depot", "market", "pier"]], "segments in a run join every stop they touch"
assert line_clusters(["north", "south", "east", "west"], [("north", "south"), ("east", "west")]) == [["east", "west"], ["north", "south"]], "separate runs stay apart and lead with their first stop"
assert line_clusters(["quay", "mill", "yard"], [("mill", "yard")]) == [["mill", "yard"], ["quay"]], "a stop no segment touches forms its own cluster"
assert line_clusters(["zoo", "arch", "kiln"], [("zoo", "kiln"), ("kiln", "arch")]) == [["arch", "kiln", "zoo"]], "a cluster lists its stops alphabetically, not as served"
assert line_clusters([], []) == [], "an operator serving no stops has no clusters"
assert line_clusters(["alpha", "beta"], [("alpha", "beta"), ("beta", "alpha"), ("alpha", "beta")]) == [["alpha", "beta"]], "a segment listed again changes nothing"
print("ok")
