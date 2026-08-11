from solution import prune_listing

assert prune_listing(["a.txt", "b.txt"], []) == ["a.txt", "b.txt"], "no rules keeps everything"
assert prune_listing(["cache", "cache/one.txt", "cachet.txt"], ["cache"]) == [
    "cachet.txt"
], "a directory rule covers itself and its contents"
assert prune_listing(["notes.tmp", "deep/notes.tmp", "tmp.notes"], ["*.tmp"]) == [
    "deep/notes.tmp",
    "tmp.notes",
], "a star rule matches from the top, inside one segment"
assert prune_listing(["kits/a.raw", "kits/sub/b.raw"], ["kits/*.raw"]) == [
    "kits/sub/b.raw"
], "a star never crosses into a deeper segment"
assert prune_listing(
    ["logs/keep.txt", "logs/spill.txt", "readme.md"], ["logs", "!logs/keep.txt"]
) == ["logs/keep.txt", "readme.md"], "a later keep rule overrides an earlier drop"
assert prune_listing(["logs/keep.txt"], ["!logs/keep.txt", "logs"]) == [], "the last matching rule decides"
assert prune_listing(["pkg/a.js", "pkg/b.js"], ["pkg", "!pkg/b*"]) == [
    "pkg/b.js"
], "a keep rule may use a star"
assert prune_listing(["free.txt"], ["bound.txt"]) == ["free.txt"], "an unmatched path survives"
assert prune_listing(["tmp", "tmp9"], ["tmp*"]) == [], "a star may match nothing"
assert prune_listing(["mycache1/x"], ["*cache*"]) == [], "two stars in one segment"
assert prune_listing([], ["x"]) == [], "an empty listing stays empty"


def rejects(listing, rules):
    try:
        prune_listing(listing, rules)
    except Exception:
        return True
    return False


assert rejects([42], []), "non-string path is rejected"
assert rejects([""], []), "empty path is rejected"
assert rejects(["a//b"], []), "doubled slash in a path is rejected"
assert rejects(["/lead"], []), "leading slash is rejected"
assert rejects(["a.txt"], [7]), "non-string rule is rejected"
assert rejects(["a.txt"], [""]), "empty rule is rejected"
assert rejects(["a.txt"], ["!"]), "bare exclamation mark is rejected"
assert rejects(["a.txt"], ["x//y"]), "empty pattern segment is rejected"
print("ok")
