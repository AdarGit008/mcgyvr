from solution import span_letters

assert span_letters("a-e") == "abcde", "the closing letter is included"
assert span_letters("c-d") == "cd", "a span of two letters"
assert span_letters("a-a") == "a", "a span opening and closing on one letter"
assert span_letters("e-a") == "e-a", "a span running backward is untouched"
assert span_letters("hello") == "hello", "a text that is not a span"
assert span_letters("") == "", "a text holding nothing"
print("ok")
