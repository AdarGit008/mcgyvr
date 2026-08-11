def mix_case(text: str) -> str:
    letters = "abcdefghijklmnopqrstuvwxyz"
    out = []
    upper = True
    for ch in text:
        if ch.lower() in letters:
            out.append(ch.upper() if upper else ch.lower())
            upper = not upper
        else:
            out.append(ch)
    return "".join(out)
