from solution import render_data_size

assert render_data_size(0) == "0B", "zero renders as 0B alone"
assert render_data_size(5) == "5B", "a few bytes stay bytes"
assert render_data_size(1024) == "1KiB", "exactly one binary kilobyte"
assert render_data_size(1023) == "1023B", "one under the ladder stays in bytes"
assert render_data_size(1048576 + 1024 + 1) == "1MiB 1KiB 1B", (
    "each nonzero rung appears once"
)
assert render_data_size(3 * 1073741824 + 2 * 1024) == "3GiB 2KiB", (
    "a zero rung between nonzero rungs is absent"
)
assert render_data_size(2047) == "1KiB 1023B", (
    "the remainder after a rung stays below that rung"
)
assert render_data_size(5 * 1073741824) == "5GiB", (
    "a round count is a single component"
)


def rejects(value):
    try:
        render_data_size(value)
    except ValueError:
        return True
    return False


assert rejects(-1), "a negative count is rejected"
assert rejects(1.5), "a fractional count is rejected"
assert rejects("1024"), "a string count is rejected"
print("ok")
