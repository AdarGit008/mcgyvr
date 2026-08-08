from solution import encode_pairs

assert encode_pairs([["a", "1"], ["b", "2"]]) == "a=1&b=2", "plain pairs"
assert encode_pairs([]) == "", "empty list gives empty string"
assert encode_pairs([["p", "100%"]]) == "p=100%25", "percent escapes"
assert encode_pairs([["q", "a&b"]]) == "q=a%26b", "ampersand escapes"
assert encode_pairs([["e", "x=y"]]) == "e=x%3Dy", "equals escapes"
assert encode_pairs([["m", "&&"]]) == "m=%26%26", "every occurrence escapes"
assert (
    encode_pairs([["k%", "=&"]]) == "k%25=%3D%26"
), "escapes never re-escape their own percent"
assert encode_pairs([["b", "2"], ["a", "1"]]) == "b=2&a=1", "order preserved"


def rejects(value):
    try:
        encode_pairs(value)
    except ValueError:
        return True
    return False


assert rejects([["", "x"]]), "empty key is rejected"
assert rejects([["a", 5]]), "non-string value is rejected"
assert rejects([[5, "a"]]), "non-string key is rejected"
print("ok")
