from solution import swatch_word

assert swatch_word("#ffffff", [5, 6, 5]) == "1111111111111111", "a white colour keeps every reduced bit set"
assert swatch_word("#000000", [5, 6, 5]) == "0000000000000000", "a black colour pads out to the summed depth"
assert swatch_word("#3a7f2b", [5, 6, 5]) == "0011101111100101", "channels are reduced then packed red first"
assert swatch_word("#804020", [3, 3, 2]) == "10001000", "uneven depths keep only the top bits of each byte"
assert swatch_word("#f0a", [4, 4, 4]) == "111100001010", "the short form doubles each digit into a byte"


def rejects(*args):
    try:
        swatch_word(*args)
    except Exception:
        return True
    return False


assert rejects("3a7f2b", [5, 6, 5]), "a colour without the leading hash is rejected"
assert rejects("#3a7f2b", [5, 6, 9]), "a depth above eight is rejected"
print("ok")
