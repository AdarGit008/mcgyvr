from solution import unpack_frames

assert unpack_frames("#0;") == [], "empty stream is just the trailer"
assert unpack_frames("5:hello;#1;") == ["hello"], "one frame decodes"
assert unpack_frames("3:abc;2:de;#2;") == ["abc", "de"], "frames in order"
assert unpack_frames("0:;#1;") == [""], "zero-length payload"
assert unpack_frames("5:a;b:c;#1;") == ["a;b:c"], "payload may hold ';' and ':'"
assert unpack_frames("2:12;#1;") == ["12"], "payload may hold digits"
assert unpack_frames("0:;3:xyz;#2;") == ["", "xyz"], "empty and full frames mix"


def rejects(stream):
    try:
        unpack_frames(stream)
    except ValueError:
        return True
    return False


assert rejects(""), "empty string lacks the trailer"
assert rejects("5:hello;"), "missing trailer"
assert rejects("9:abc;#1;"), "truncated payload"
assert rejects("3:abc"), "unterminated frame"
assert rejects("3:abc#1;"), "frame closed by wrong char"
assert rejects("03:abc;#1;"), "leading-zero length"
assert rejects(":abc;#1;"), "missing length"
assert rejects("3;abc;#1;"), "length without ':'"
assert rejects(42), "non-string stream"
assert rejects("3:abc;#2;"), "count mismatch"
assert rejects("3:abc;#1;x"), "text after the trailer"
print("ok")
