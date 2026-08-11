def cap_after(passage: str) -> str:
    letters = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
    out = ""
    fresh = True
    for ch in passage:
        if fresh and ch in letters:
            out += ch.upper()
            fresh = False
        else:
            out += ch
        if ch == ".":
            fresh = True
    return out
