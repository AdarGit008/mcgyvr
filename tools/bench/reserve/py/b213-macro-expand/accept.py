from solution import expand_macro

BOOK = {"who": "world", "greet": "hello $(who)", "loud": "$(greet)!"}


def rejects(text, macros):
    try:
        expand_macro(text, macros)
    except ValueError:
        return True
    return False


assert expand_macro("nothing to swap", {}) == "nothing to swap", "text without references is untouched"
assert expand_macro("$(who)", BOOK) == "world", "a plain reference takes its value"
assert expand_macro("greeting: $(greet)!", BOOK) == "greeting: hello world!", "a value is read for references in turn"
assert expand_macro("$(loud)", BOOK) == "hello world!", "a macro reaches through two others"
assert expand_macro("[$(absent)]", BOOK) == "[]", "an unknown name with no fallback vanishes"
assert expand_macro("[$(absent:none set)]", BOOK) == "[none set]", "an unknown name falls back as written"
assert rejects("$(one)", {"one": "$(two)", "two": "$(one)"}), "a cycle of macros is rejected"
print("ok")
