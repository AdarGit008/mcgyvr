def decode_escaped_note(text: str) -> str:
    lines = [line.rstrip(" \t") for line in text.split("\n")]
    folded = lines[0]
    for line in lines[1:]:
        if folded.endswith("="):
            folded = folded[:-1] + line
        else:
            folded = folded + "\n" + line
    out = ""
    i = 0
    while i < len(folded):
        if folded[i] == "=":
            pair = folded[i + 1 : i + 3]
            if len(pair) != 2 or any(c not in "0123456789ABCDEF" for c in pair):
                raise ValueError("bad escape in note")
            out += chr(int(pair, 16))
            i += 3
        else:
            out += folded[i]
            i += 1
    return out
