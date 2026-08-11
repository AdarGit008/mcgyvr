from solution import clean_recipients

assert clean_recipients(["  Ana.Lee@Mail.Example.com  "]) == [
    "Ana.Lee@mail.example.com"
], "trims and lowercases only the domain"
assert clean_recipients(["Kim@a.io", "jo@b.co", "kim@A.IO"]) == [
    "Kim@a.io",
    "jo@b.co",
], "a distant duplicate is dropped case-insensitively"
assert clean_recipients(["Dana Reyes <Dana@Ops.example>"]) == [
    "Dana@ops.example"
], "a display entry keeps only its bracketed address"
assert clean_recipients(["ed@hq.example", "Ed <ED@HQ.example>"]) == [
    "ed@hq.example"
], "a display duplicate is dropped too"
assert clean_recipients([]) == [], "no entries, no addresses"
assert clean_recipients(["Team <  crew@list.example.org  >"]) == [
    "crew@list.example.org"
], "padding inside the brackets trims away"


def rejects(raw):
    try:
        clean_recipients(raw)
    except Exception:
        return True
    return False


assert rejects("solo@one.example"), "a bare string"
assert rejects([7]), "a numeric entry is rejected"
assert rejects(["plainname"]), "no @ at all"
assert rejects(["pat@@dual.example"]), "two @ signs"
assert rejects(["@lone.example"]), "an empty local part"
assert rejects(["pat@host"]), "a dotless domain"
assert rejects(["pat@host.example."]), "a trailing dot"
assert rejects(["pa t@host.example"]), "inner whitespace"
assert rejects(["Dana <pat@host.example> yes"]), "text after the closing bracket"
print("ok")
