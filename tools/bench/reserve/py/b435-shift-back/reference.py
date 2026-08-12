def shift_back(text: str, places: int) -> str:
    alphabet = "abcdefghijklmnopqrstuvwxyz"
    out = ""
    for ch in text:
        at = alphabet.find(ch)
        if at == -1:
            out += ch
        else:
            out += alphabet[(at - places) % 26]
    return out
