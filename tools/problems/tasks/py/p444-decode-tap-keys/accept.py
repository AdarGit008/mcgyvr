from solution import decode_tap_keys


def rejects(value):
    try:
        decode_tap_keys(value)
    except ValueError:
        return True
    return False


assert decode_tap_keys("4433555-555666") == "HELLO", "a hyphen parts two letters on key 5"
assert decode_tap_keys("96667773") == "WORD", "runs on different keys need no hyphen"
assert decode_tap_keys("6-666-666-66") == "MOON", "three parted runs on key 6"
assert decode_tap_keys("84433") == "THE", "one tap then two then two"
assert decode_tap_keys("44-0-44") == "H H", "key 0 is a space"
assert decode_tap_keys("0") == " ", "a lone space"
assert decode_tap_keys("9999") == "Z", "the fourth letter of a four-letter key"
assert decode_tap_keys("7777") == "S", "four taps of 7 reach S"
assert decode_tap_keys("2") == "A", "a single tap"

assert rejects(""), "an empty sequence is refused"
assert rejects(88), "a non-string is refused"
assert rejects("2222"), "a run past the end of a key is refused"
assert rejects("00"), "two taps of 0 are refused"
assert rejects("77777"), "five taps of 7 are refused"
assert rejects("144"), "key 1 is refused"
assert rejects("4a4"), "a stray character is refused"
assert rejects("-44"), "a leading hyphen is refused"
assert rejects("44-"), "a trailing hyphen is refused"
assert rejects("44--33"), "two hyphens in a row are refused"
print("ok")
