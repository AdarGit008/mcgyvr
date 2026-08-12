from solution import camel_break

assert camel_break("orderId") == ["order", "id"], "a capital opens a word"
assert camel_break("id") == ["id"], "no capitals, one word"
assert camel_break("OrderId") == ["order", "id"], "a leading capital adds nothing"
assert camel_break("abc") == ["abc"], "a plain word"
assert camel_break("") == [], "nothing to break"
assert camel_break("aBcD") == ["a", "bc", "d"], "several short words"
assert camel_break("http2Server") == ["http2", "server"], "a digit opens nothing"
print("ok")
