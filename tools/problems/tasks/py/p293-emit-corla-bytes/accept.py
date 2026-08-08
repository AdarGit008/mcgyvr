from solution import emit_corla_bytes


def rejects(listing):
    try:
        emit_corla_bytes(listing)
    except ValueError:
        return True
    return False


assert emit_corla_bytes([]) == [], "an empty listing settles no bytes"
assert emit_corla_bytes(["# only a note", "", "  ", ".idle"]) == [], (
    "notes, blank rows and a spot occupy nothing"
)
assert emit_corla_bytes(["NOP", "STOP", "LOAD 0", "LOAD 255"]) == [
    0,
    64,
    16,
    0,
    16,
    255,
], "the one and two byte keywords lay down in order"
assert emit_corla_bytes(
    [
        "# a small routine",
        ".top",
        "LOAD 7",
        "CALL .helper",
        "GOTO .done",
        ".helper",
        "NOP",
        "STOP",
        ".done",
        "STOP",
    ]
) == [16, 7, 48, 0, 8, 32, 0, 10, 0, 64, 64], (
    "spots further down the listing carry their true byte address"
)
assert emit_corla_bytes([".begin", "NOP", "GOTO .begin"]) == [0, 32, 0, 0], (
    "a spot already passed still resolves"
)

wide = ["GOTO .far"] + ["NOP"] * 300 + [".far", "STOP"]
wide_bytes = emit_corla_bytes(wide)
assert wide_bytes[0:3] == [32, 1, 47], (
    "an address past 255 splits into a high and a low byte"
)
assert len(wide_bytes) == 304, "three bytes, three hundred, then one"

assert rejects("NOP"), "text is not a list of rows"
assert rejects([12]), "a row must be text"
assert rejects(["JUMP .x", ".x"]), "JUMP is no keyword"
assert rejects(["NOP 1"]), "NOP carries no argument"
assert rejects(["LOAD"]), "LOAD wants its v"
assert rejects(["LOAD 256"]), "256 is past the ceiling"
assert rejects(["GOTO .gone"]), "no row names gone"
assert rejects([".done", "NOP", "GOTO done"]), (
    "an argument spot keeps its full stop"
)
assert rejects([".Twice", "NOP"]), "a spot is spelled in lowercase"
assert rejects([".same", "NOP", ".same", "NOP"]), "a spot may be named only once"
print("ok")
