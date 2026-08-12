from solution import field_mean

assert field_mean([{"a": 1}, {"a": 3}], "a") == 2, "the mean of two"
assert field_mean([{"a": 1}], "a") == 1, "one record"
assert field_mean([], "a") == 0, "no records at all"
assert field_mean([{"b": 1}], "a") == 0, "no record carries the field"
assert field_mean([{"a": 1}, {"b": 2}], "a") == 1, "the other record is passed over"
assert field_mean([{"a": 1}, {"a": 2}], "a") == 1, "the mean is rounded down"
print("ok")
