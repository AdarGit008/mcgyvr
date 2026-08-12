from solution import parse_option, scan_pairs

assert scan_pairs("mode=fast") == [["mode", "fast"]], "single pair"
assert scan_pairs("a=1;b=two;c=3") == [
    ["a", "1"],
    ["b", "two"],
    ["c", "3"],
], "several pairs keep input order"
assert scan_pairs('note="x;y";flag=on') == [
    ["note", "x;y"],
    ["flag", "on"],
], "a quoted semicolon does not split"
assert scan_pairs("label=") == [["label", ""]], "bare empty value"
assert scan_pairs('empty=""') == [["empty", ""]], "quoted empty value"
assert parse_option('depth="3;4"') == ["depth", "3;4"], "helper unquotes"


def rejects(value):
    try:
        scan_pairs(value)
    except Exception:
        return True
    return False


assert rejects(42), "non-string is rejected"
assert rejects(""), "empty string is rejected"
assert rejects("a=1;;b=2"), "empty segment is rejected"
assert rejects("1a=x"), "non-bare key is rejected"
assert rejects("dup=1;dup=2"), "repeated key is rejected"
assert rejects('q="abc'), "unterminated quote is rejected"
print("ok")
