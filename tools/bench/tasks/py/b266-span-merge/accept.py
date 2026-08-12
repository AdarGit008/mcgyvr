from solution import span_merge

assert span_merge([[1, 3], [2, 5]]) == [[1, 5]], "two overlapping spans"
assert span_merge([[1, 2], [2, 4]]) == [[1, 4]], "touching end to start"
assert span_merge([[5, 6], [1, 2]]) == [[1, 2], [5, 6]], "sorted by start"
assert span_merge([[1, 10], [2, 3]]) == [[1, 10]], "one span swallows another"
assert span_merge([[1, 2], [4, 5]]) == [[1, 2], [4, 5]], "a real gap survives"
assert span_merge([]) == [], "no spans at all"
print("ok")
