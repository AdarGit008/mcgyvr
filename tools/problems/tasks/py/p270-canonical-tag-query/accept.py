from solution import canonical_tag_query

assert canonical_tag_query("") == "", "an empty query stays empty"
assert canonical_tag_query("a:1") == "a:1", "a single item passes through"
assert canonical_tag_query("b:2;a:1") == "a:1;b:2", "items are put in key order"
assert canonical_tag_query("a:1;a:1") == "a:1", "an exact repeat collapses"
assert canonical_tag_query("a:2;a:1") == "a:1;a:2", "a shared key orders by value"
assert canonical_tag_query("m:9;m:9;m:8;n:1") == "m:8;m:9;n:1", "repeats collapse while the rest reorder"
assert canonical_tag_query("a:1;A:2") == "A:2;a:1", "upper case sorts ahead of lower case"
assert canonical_tag_query("a:") == "a:", "an empty value is allowed"
assert canonical_tag_query("z~3Ax:1") == "z~3Ax:1", "a colon inside a key survives the round trip"
assert canonical_tag_query("a:~3B") == "a:~3B", "a semicolon inside a value survives the round trip"
assert canonical_tag_query("~7E:1") == "~7E:1", "a tilde inside a key survives the round trip"
assert canonical_tag_query("a~20b:1;ab:2") == "a b:1;ab:2", "a space needs no escape once decoded"
assert canonical_tag_query("a~3Ax:1;ab:2") == "a~3Ax:1;ab:2", "ordering follows the decoded key, not the written one"
assert canonical_tag_query("tag:~7E~3A~3B") == "tag:~7E~3A~3B", "all three special glyphs in one value"


def rejects(value):
    try:
        canonical_tag_query(value)
    except ValueError:
        return True
    return False


assert rejects("a1"), "an item with no colon"
assert rejects("a:1;"), "a trailing separator leaves an empty item"
assert rejects(":1"), "an empty key"
assert rejects("a:1:2"), "a second bare colon"
assert rejects("a:~3"), "an escape cut short"
assert rejects("a:~zz"), "an escape that is not hex"
assert rejects("a:~3a"), "a lower-case hex escape"
assert rejects("a:~7F"), "an escape above the printable band"
assert rejects("a:~1F"), "an escape below the printable band"
assert rejects("a:\t1"), "a raw glyph outside the printable band"
assert rejects(5), "a query that is not text"
print("ok")
