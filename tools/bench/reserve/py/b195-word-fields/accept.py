from solution import describe_word

assert describe_word(41000, [["value", 16]]) == "value=41000", "one field covers the whole word"
assert describe_word(43981, [["hi", 8], ["lo", 8]]) == "hi=171,lo=205", "fields are cut most significant first"
assert describe_word(32769, [["alarm", 1], ["mid", 14], ["ready", 1]]) == "alarm=on,mid=0,ready=on", "a set one-bit field reads on"
assert describe_word(0, [["alarm", 1], ["mid", 14], ["ready", 1]]) == "alarm=off,mid=0,ready=off", "a clear one-bit field reads off"
assert describe_word(42458, [["mode", 2], ["gain", 6], ["fast", 1], ["level", 7]]) == "mode=2,gain=37,fast=on,level=90", "widths of every size are cut in turn"


def rejects(*args):
    try:
        describe_word(*args)
    except ValueError:
        return True
    return False


assert rejects(0, [["a", 8], ["b", 7]]), "widths short of sixteen bits are rejected"
print("ok")
