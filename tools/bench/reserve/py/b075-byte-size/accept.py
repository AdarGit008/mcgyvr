from solution import parse_byte_size

assert parse_byte_size("512B") == 512, "plain bytes"
assert parse_byte_size("4KiB") == 4096, "kibibytes"
assert parse_byte_size("3MiB") == 3145728, "mebibytes"
assert parse_byte_size("2GiB") == 2147483648, "gibibytes"
assert parse_byte_size("0B") == 0, "a zero count is zero bytes"


def rejects(value):
    try:
        parse_byte_size(value)
    except ValueError:
        return True
    return False


assert rejects(42), "non-string is rejected"
assert rejects(""), "empty string is rejected"
assert rejects("KiB"), "missing count is rejected"
assert rejects("12"), "missing unit is rejected"
assert rejects("12KB"), "decimal spelling is unknown"
assert rejects("12 KiB"), "stray character is rejected"
print("ok")
