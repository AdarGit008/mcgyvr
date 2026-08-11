from solution import tag_open, tag_pair


def rejects(call, *args):
    try:
        call(*args)
    except Exception:
        return True
    return False


assert tag_open("<p>") == "p", "an opening marker names itself"
assert tag_open("</p>") == "p", "the slash is dropped"
assert tag_pair("<div>", "</div>") is True, "a matched pair"
assert tag_pair("<div>", "</span>") is False, "a mismatched pair"
assert rejects(tag_open, "p"), "an unbracketed marker is rejected"
assert rejects(tag_pair, "<p>", "p"), "either side may be rejected"
print("ok")
