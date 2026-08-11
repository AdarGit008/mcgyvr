from solution import cloud_code

assert cloud_code({"CL": "clear"}, "CL") == "clear", "a plain lookup"
assert cloud_code({"CL": "clear"}, "cl") == "clear", "lower case still matches"
assert cloud_code({"RN": "rain"}, "Rn") == "rain", "mixed case still matches"
assert cloud_code({"CL": "clear"}, "RN") == "unknown", "a code not in the table"
assert cloud_code({}, "CL") == "unknown", "an empty table"
assert cloud_code({"CL": ""}, "CL") == "", "an empty description is not unknown"
print("ok")
