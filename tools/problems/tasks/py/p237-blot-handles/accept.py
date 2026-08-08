from solution import blot_handles


def rejects(message):
    try:
        blot_handles(message)
    except ValueError:
        return True
    return False


assert blot_handles("") == "", "an empty message stays empty"
assert blot_handles("hi @alice_1 there") == "hi @a...... there", (
    "the at sign and the first character survive the blot"
)
assert blot_handles("ping @zed!") == "ping @z..!", (
    "three characters is the shortest handle there is"
)
assert blot_handles("@ab and @abcdefghijklm") == "@ab and @abcdefghijklm", (
    "two characters and thirteen are both no handle"
)
assert blot_handles("mail me@home now") == "mail me@home now", (
    "an at sign glued to a word is an address, not a handle"
)
assert blot_handles("@abc@def") == "@a..@def", (
    "the second at sign follows a handle character, so it opens nothing"
)
assert blot_handles("@aaa @bbb") == "@a.. @b..", (
    "each handle in a plain part is blotted"
)
assert blot_handles("run `@bob` but @carol here") == "run `@bob` but @c.... here", (
    "a fenced handle is copied through with its backticks"
)
assert blot_handles("@dave ` @erin") == "@d... ` @erin", (
    "a backtick with no partner fences the rest of the message"
)
assert blot_handles("`@one` `@two` @three") == "`@one` `@two` @t....", (
    "fences alternate, so the text between two of them is plain"
)
assert blot_handles("@a_9 done") == "@a.. done", (
    "digits and underscores count toward the length"
)
assert rejects(7), "a number is not a message"
print("ok")
