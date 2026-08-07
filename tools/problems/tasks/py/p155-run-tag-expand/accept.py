from solution import expand_run_tag

assert expand_run_tag("cam-[2-10/4]") == [
    "cam-10",
    "cam-2",
    "cam-6",
], "stepped run, sorted as strings"
assert expand_run_tag("led[red,green,blue].cfg") == [
    "ledblue.cfg",
    "ledgreen.cfg",
    "ledred.cfg",
], "comma listing keeps stem and tail"
assert expand_run_tag("[7-9]") == ["7", "8", "9"], "bare run"
assert expand_run_tag("x[a,a]") == ["xa"], "duplicates collapse"
assert expand_run_tag("[0-0]") == ["0"], "one-value run"
assert expand_run_tag("n[1-3]s") == ["n1s", "n2s", "n3s"], "slashless run steps by one"


def rejects(value):
    try:
        expand_run_tag(value)
    except ValueError:
        return True
    return False


assert rejects("nope"), "pattern without a group"
assert rejects("a[b"), "unclosed bracket"
assert rejects("]x["), "reversed brackets"
assert rejects("a[]b"), "empty body"
assert rejects("a[x,,y]"), "empty comma item"
assert rejects("[3-1]"), "descending run"
assert rejects("[1-9/0]"), "zero step"
assert rejects("[1-2][3-4]"), "two groups"
assert rejects(5), "non-string argument"
print("ok")
