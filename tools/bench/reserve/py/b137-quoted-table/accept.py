from solution import parse_quoted_table

assert parse_quoted_table("a,b\nc,d") == [["a", "b"], ["c", "d"]], "plain rows"
assert parse_quoted_table("note") == [["note"]], "one bare field"
assert parse_quoted_table('"a,b",c') == [["a,b", "c"]], "comma inside quotes"
assert parse_quoted_table('"say ""hi""",x') == [
    ['say "hi"', "x"]
], "doubled quote becomes one literal quote"
assert parse_quoted_table('"line one\nline two",z\nq,r') == [
    ["line one\nline two", "z"],
    ["q", "r"],
], "newline inside quotes stays in the field"
assert parse_quoted_table("a,,c") == [["a", "", "c"]], "empty field between commas"
assert parse_quoted_table('"",b') == [["", "b"]], "quoted empty field"
assert parse_quoted_table("a,b\n") == [["a", "b"]], "one final newline opens no row"
assert parse_quoted_table(",\n,") == [["", ""], ["", ""]], "rows of empty fields"
assert parse_quoted_table('"a"\nb') == [["a"], ["b"]], "quoted equals unquoted"


def rejects(value):
    try:
        parse_quoted_table(value)
    except ValueError:
        return True
    return False


assert rejects(42), "non-string is rejected"
assert rejects(""), "empty text is rejected"
assert rejects("a\rb"), "carriage return is rejected"
assert rejects('a"b,c'), "quote in unquoted field is rejected"
assert rejects('"abc'), "unclosed quote is rejected"
assert rejects('"a"x,b'), "junk after closing quote is rejected"
assert rejects("a,b\nc"), "ragged row is rejected"
print("ok")
