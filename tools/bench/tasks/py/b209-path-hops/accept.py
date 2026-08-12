from solution import path_hops

assert path_hops("a/b/c", "a/b/c") == 0, "the same directory is no hops away"
assert path_hops("a/b", "a/b/c/d") == 2, "walking down costs one hop per segment"
assert path_hops("a/b/c", "a") == 2, "walking up costs one hop per segment"
assert path_hops("a/b/c", "a/x/y") == 4, "a sibling branch costs the climb and the descent"
assert path_hops("a/./b/../c", "a/c") == 0, "dot and two-dot segments are reduced first"
assert path_hops("", "a") == 1, "the empty path is the root"


def rejects(*args):
    try:
        path_hops(*args)
    except Exception:
        return True
    return False


assert rejects("a/../..", "a"), "climbing above the root is rejected"
print("ok")
