from solution import size_unit, size_text


def rejects(value):
    try:
        size_text(value)
    except Exception:
        return True
    return False


assert size_unit(500) == "B", "under a kilobyte"
assert size_unit(2000) == "KB", "over a kilobyte"
assert size_text(500) == "500 B", "written in bytes"
assert size_text(3000) == "2 KB", "a kilobyte is 1024 bytes"
assert size_text(1024) == "1 KB", "exactly one kilobyte"
assert size_text(0) == "0 B", "nothing at all"
assert rejects(-1), "a negative count is rejected"
print("ok")
