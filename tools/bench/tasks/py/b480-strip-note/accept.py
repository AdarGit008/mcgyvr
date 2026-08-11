from solution import strip_note

assert strip_note("Report (draft)") == "Report", "a closing note is removed"
assert strip_note("Report (draft) final") == "Report (draft) final", "a note that does not close at the end stays"
assert strip_note("Plain title") == "Plain title", "a title with no bracket"
assert strip_note("Notes (a) (b)") == "Notes (a)", "only the closing note goes"
assert strip_note("Song (live)") == "Song", "spaces left trailing are removed"
assert strip_note("") == "", "a title holding nothing"
print("ok")
