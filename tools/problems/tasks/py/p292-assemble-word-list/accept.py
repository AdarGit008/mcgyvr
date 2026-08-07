from solution import assemble_word_list


def rejects(lines):
    try:
        assemble_word_list(lines)
    except ValueError:
        return True
    return False


assert assemble_word_list([]) == [], "an empty source assembles to no words"
assert assemble_word_list(["; nothing but a remark", "   ", "spot:"]) == [], (
    "remarks, blank lines and a marker take no word"
)
assert assemble_word_list(["HALT"]) == [16384], "HALT is a bare mnemonic"
assert assemble_word_list(["SET r0, 0", "SET r7, 255"]) == [4096, 6143], (
    "the register rides the 256 place and the immediate the ones"
)
assert assemble_word_list(["ADD r3,r5"]) == [8965], (
    "commas need no surrounding space"
)
assert assemble_word_list(
    [
        "; wind down",
        "  SET r1, 3",
        "loop:",
        "  ADD r1, r2",
        "  JZ r1, done",
        "  JZ r0, loop",
        "done:",
        "  HALT",
    ]
) == [4355, 8450, 12545, 12541, 16384], "markers resolve both forward and backward"
assert assemble_word_list(["JZ r0, end", "end:"]) == [12288], (
    "a marker on the very next word is distance zero"
)
assert assemble_word_list(["here:", "JZ r3, here"]) == [13311], (
    "a jump onto itself is distance minus one"
)

reach = ["far:"] + ["HALT"] * 127 + ["JZ r0, far"]
assert assemble_word_list(reach)[127] == 12288 + 128, (
    "minus 128 is the furthest backward distance that still fits"
)

overreach = ["far:"] + ["HALT"] * 128 + ["JZ r0, far"]
assert rejects(overreach), "one word further back is out of range"

assert rejects("SET r0, 1"), "a string is not a list"
assert rejects([7]), "a line must be a string"
assert rejects(["MOVE r1, r2"]), "MOVE is no mnemonic"
assert rejects(["HALT r1"]), "HALT takes no operand"
assert rejects(["SET r1"]), "SET takes two operands"
assert rejects(["SET r8, 1"]), "there is no r8"
assert rejects(["SET r1, 256"]), "256 will not fit"
assert rejects(["ADD r1, 4"]), "ADD wants a register"
assert rejects(["JZ r1, gone"]), "no line plants gone"
assert rejects(["twice:", "HALT", "twice:", "HALT"]), (
    "a marker may be planted only once"
)
assert rejects(["set r1, 2"]), "mnemonics are capitals"
print("ok")
