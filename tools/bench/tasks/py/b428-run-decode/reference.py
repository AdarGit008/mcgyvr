def run_decode(coded: str) -> str:
    out = ""
    i = 0
    while i < len(coded):
        letter = coded[i]
        i += 1
        digits = ""
        while i < len(coded) and "0" <= coded[i] <= "9":
            digits += coded[i]
            i += 1
        out += letter * int(digits)
    return out
