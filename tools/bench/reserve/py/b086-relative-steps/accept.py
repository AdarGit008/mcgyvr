from solution import relative_steps, split_absolute

assert relative_steps("/srv/app", "/srv/static/logo.png") == "../static/logo.png", (
    "climb once then descend"
)
assert relative_steps("/data/sets/raw", "/data") == "../..", "pure climb to an ancestor"
assert relative_steps("/home/kim", "/home/kim") == ".", "same directory is a dot"
assert relative_steps("/", "/etc/motd") == "etc/motd", "descent from the root"
assert relative_steps("/var/tmp", "/") == "../..", "climb all the way to the root"
assert split_absolute("/usr/local/bin") == ["usr", "local", "bin"], "helper splits segments"
assert split_absolute("/") == [], "helper yields nothing for the root"


def rejects(*args):
    try:
        relative_steps(*args)
    except Exception:
        return True
    return False


assert rejects(7, "/x"), "non-string is rejected"
assert rejects("srv/app", "/x"), "relative origin is rejected"
assert rejects("/a//b", "/x"), "doubled slash is rejected"
assert rejects("/a/b/", "/x"), "trailing slash is rejected"
assert rejects("/a/../b", "/x"), "dot-dot segment is rejected"
print("ok")
