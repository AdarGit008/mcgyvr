from solution import pack_entries

assert pack_entries([["host", "alpha"]]) == "host=alpha", "a single plain pair"
assert pack_entries([["a", "1"], ["b", "2"]]) == "a=1;b=2", "pairs keep their order"
assert pack_entries([["k;1", "a=b"]]) == "k\\;1=a\\=b", "separators inside are escaped"
assert pack_entries([["path", "c:\\tmp"]]) == "path=c:\\\\tmp", "a backslash is escaped"
assert pack_entries([["list", "x;y"]]) == "list=x\\;y", "a semicolon is escaped"
assert pack_entries([["empty", ""]]) == "empty=", "an empty value is allowed"
assert pack_entries([]) == "", "no pairs yield the empty string"


def rejects(value):
    try:
        pack_entries(value)
    except Exception:
        return True
    return False


assert rejects([["", "v"]]), "an empty key is rejected"
assert rejects([["a", "1"], ["a", "2"]]), "a repeated key is rejected"
assert rejects([["a", 5]]), "a non-string value is rejected"
assert rejects([["only"]]), "a one-element entry is rejected"
assert rejects("a=1"), "a non-list argument is rejected"
print("ok")
