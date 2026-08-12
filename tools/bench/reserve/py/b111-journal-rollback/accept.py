from solution import rollback_journal

assert rollback_journal(["a", "b"], [], 0) == ["a", "b"], "zero rollback copies"
doc = ["z", "a", "m", "b"]
journal = [["insert", 1, "m"], ["insert", 0, "z"]]
assert rollback_journal(doc, journal, 2) == [
    "a",
    "b",
], "entries unwind newest first across nearby indexes"
assert doc == ["z", "a", "m", "b"], "the argument is left unmodified"
assert rollback_journal(doc, journal, 1) == [
    "a",
    "m",
    "b",
], "a partial rollback undoes only the newest entry"
assert rollback_journal(["a", "c"], [["delete", 1, "b"]], 1) == [
    "a",
    "b",
    "c",
], "a delete is undone by putting its line back"
assert rollback_journal(["a", "B"], [["replace", 1, "b", "B"]], 1) == [
    "a",
    "b",
], "a replace is undone by restoring its before text"
assert rollback_journal(
    ["cap"], [["delete", 1, "tail"], ["replace", 0, "cup", "cap"]], 2
) == ["cup", "tail"], "mixed kinds unwind in reverse order"


def rejects(*args):
    try:
        rollback_journal(*args)
    except Exception:
        return True
    return False


assert rejects(["a", 1], [], 0), "a non-string line is rejected"
assert rejects(["a"], "x", 0), "a non-list journal is rejected"
assert rejects(["a"], [["insert", 0, "a"]], 2), "a count past the journal is rejected"
assert rejects(["a"], [["insert", 0]], 1), "an entry missing its fields is rejected"
assert rejects(["a"], [["insert", 5, "a"]], 1), "an index outside the document is rejected"
assert rejects(["a"], [["insert", 0, "b"]], 1), "an insert whose text misses its line is rejected"
assert rejects(["a"], [["replace", 0, "b", "c"]], 1), "a replace whose after text misses its line is rejected"
print("ok")
