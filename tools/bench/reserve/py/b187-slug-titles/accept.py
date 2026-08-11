from solution import slug_titles

assert slug_titles([]) == [], "no titles yields no slugs"
assert slug_titles(["Bridge Repairs Begin"]) == ["bridge-repairs-begin"], "spaces become single hyphens"
assert slug_titles(["  ...Ferry Times, Revised!  "]) == ["ferry-times-revised"], "runs of punctuation collapse and the ends stay clean"
assert slug_titles(["Pier 9 Reopens"]) == ["pier-9-reopens"], "digits survive the fold"
assert slug_titles(["Tide Table", "Tide table", "TIDE  TABLE"]) == ["tide-table", "tide-table-2", "tide-table-3"], "later claimants take their ordinal"


def rejects(value):
    try:
        slug_titles(value)
    except Exception:
        return True
    return False


assert rejects(["fine", 7]), "a title that is not a string is rejected"
assert rejects(["!!!"]), "a title with no letter or digit is rejected"
print("ok")
