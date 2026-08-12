import re


def mask_from_prefix(prefix):
    if isinstance(prefix, bool) or not isinstance(prefix, int) or not 0 <= prefix <= 32:
        raise ValueError("prefix must be an integer from 0 to 32")
    octets = []
    for slot in range(4):
        ones = min(8, max(0, prefix - slot * 8))
        octets.append(str(256 - 2 ** (8 - ones)))
    return ".".join(octets)


def prefix_from_mask(mask):
    if not isinstance(mask, str):
        raise ValueError("mask must be a string")
    fields = mask.split(".")
    if len(fields) != 4:
        raise ValueError("a mask is four dot-separated octets")
    value = 0
    for field in fields:
        if not re.fullmatch(r"[0-9]+", field):
            raise ValueError("octet fields must be decimal digits")
        if field != "0" and field.startswith("0"):
            raise ValueError("octet fields must not carry leading zeros")
        octet = int(field)
        if octet > 255:
            raise ValueError("octets must lie from 0 to 255")
        value = value * 256 + octet
    ones = 0
    ended = False
    for bit in range(31, -1, -1):
        if value >> bit & 1:
            if ended:
                raise ValueError("mask one bits must form one unbroken run")
            ones += 1
        else:
            ended = True
    return ones
