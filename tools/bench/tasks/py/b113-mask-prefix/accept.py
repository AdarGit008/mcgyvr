from solution import mask_from_prefix, prefix_from_mask

assert mask_from_prefix(0) == "0.0.0.0", "no ones renders all zeros"
assert mask_from_prefix(20) == "255.255.240.0", "a mid-octet prefix renders"


def prefix_rejects(value):
    try:
        mask_from_prefix(value)
    except ValueError:
        return True
    return False


assert prefix_rejects(33), "a prefix past 32 is rejected"
assert prefix_from_mask("0.0.0.0") == 0, "all zeros reads back as 0"
assert prefix_from_mask("255.255.240.0") == 20, "a mid-octet mask reads back"
assert prefix_from_mask("255.255.255.255") == 32, "all ones reads back as 32"
assert prefix_from_mask(mask_from_prefix(11)) == 11, "the two directions agree"


def rejects(value):
    try:
        prefix_from_mask(value)
    except ValueError:
        return True
    return False


assert rejects(7), "a non-string mask is rejected"
assert rejects("255.255.240"), "three fields are rejected"
assert rejects("255.x.0.0"), "a non-digit field is rejected"
assert rejects("255.040.0.0"), "a leading zero is rejected"
assert rejects("256.0.0.0"), "an octet past 255 is rejected"
assert rejects("255.0.255.0"), "a bit run broken across octets is rejected"
assert rejects("250.0.0.0"), "a bit run broken inside an octet is rejected"
print("ok")
