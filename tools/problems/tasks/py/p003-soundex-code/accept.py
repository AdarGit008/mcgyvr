from solution import soundex_code

assert soundex_code("Robert") == "R163", "Robert"
assert soundex_code("Rupert") == "R163", "Rupert matches Robert"
assert soundex_code("Ashcraft") == "A261", "h between same digits collapses"
assert soundex_code("Tymczak") == "T522", "adjacent same digits collapse"
assert soundex_code("Pfister") == "P236", "first letter joins collapsing"
assert soundex_code("Jackson") == "J250", "vowel after first letter keeps next"
assert soundex_code("Honeyman") == "H555", "vowel between same digits keeps both"
assert soundex_code("washington") == "W252", "lowercase input, truncation"
assert soundex_code("Euler") == "E460", "padding to three digits"
assert soundex_code("a") == "A000", "single letter pads with zeros"


def rejects(value):
    try:
        soundex_code(value)
    except ValueError:
        return True
    return False


assert rejects(""), "empty word is rejected"
assert rejects("van Dyk"), "space is rejected"
assert rejects("O'Brien"), "apostrophe is rejected"
assert rejects(42), "non-string is rejected"
print("ok")
