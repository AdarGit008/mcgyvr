from solution import mask_fault

assert mask_fault("report-*.log") == "ok", "wildcards and a literal dash are sound"
assert mask_fault("[a-z][0-9]?.txt") == "ok", "two closed classes with rising ranges are sound"
assert mask_fault("draft\\[1\\].txt") == "ok", "an escaped bracket opens no class"
assert mask_fault("trail\\") == "dangling escape at 5", "a trailing backslash is met at its own index"
assert mask_fault("size[0-9") == "unclosed class at 4", "an unclosed class is named at its bracket"
assert mask_fault("[z-a].log") == "reversed range at 1", "a range ending below its start is named at the start"
assert mask_fault("[9-1]x\\") == "reversed range at 1", "the class closes before the trailing backslash is met"
print("ok")
