def radix_value(literal):
    if not isinstance(literal, str):
        raise ValueError("radix_value expects a string")
    base_part, mark, digits = literal.partition("#")
    if mark == "": raise ValueError("literal needs a hash mark")
    if not base_part.isdigit() or not 2 <= int(base_part) <= 16:
        raise ValueError("base must be a decimal number from 2 to 16")
    if digits == "": raise ValueError("digit part is empty")
    base, value = int(base_part), 0
    for ch in digits:
        worth = "0123456789abcdef".find(ch)
        if worth < 0 or worth >= base: raise ValueError("a digit must be valued under the base")
        value = value * base + worth
    return value
