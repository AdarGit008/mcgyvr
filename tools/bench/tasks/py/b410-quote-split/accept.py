from solution import in_quote, quote_split

assert in_quote('"') is True, "the quotation mark"
assert in_quote("a") is False, "an ordinary character"
assert quote_split("a,b") == ["a", "b"], "a plain break"
assert quote_split('"a,b"') == ['"a,b"'], "a quoted comma does not break"
assert quote_split("") == [""], "an empty line is one empty piece"
assert quote_split('a,"b,c",d') == [
    "a",
    '"b,c"',
    "d",
], "a quoted piece among plain ones"
print("ok")
