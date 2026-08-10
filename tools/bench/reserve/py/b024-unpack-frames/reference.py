"""Decode a framed wire string: length-prefixed frames, then a count trailer."""


def _scan_digits(stream, start):
    cursor = start
    while cursor < len(stream) and "0" <= stream[cursor] <= "9":
        cursor += 1
    return stream[start:cursor], cursor


def unpack_frames(stream: str) -> list:
    if not isinstance(stream, str):
        raise ValueError("stream must be a string")
    frames = []
    cursor = 0
    while cursor < len(stream) and stream[cursor] != "#":
        digits, cursor = _scan_digits(stream, cursor)
        if not digits:
            raise ValueError("frame length is missing")
        if len(digits) > 1 and digits[0] == "0":
            raise ValueError("frame length has a leading zero")
        if cursor >= len(stream) or stream[cursor] != ":":
            raise ValueError("expected ':' after the frame length")
        cursor += 1
        length = int(digits)
        if cursor + length > len(stream):
            raise ValueError("frame payload is truncated")
        frames.append(stream[cursor : cursor + length])
        cursor += length
        if cursor >= len(stream) or stream[cursor] != ";":
            raise ValueError("frame is not terminated")
        cursor += 1
    if cursor >= len(stream) or stream[cursor] != "#":
        raise ValueError("count trailer is missing")
    cursor += 1
    count_digits, cursor = _scan_digits(stream, cursor)
    if not count_digits:
        raise ValueError("trailer count is missing")
    if len(count_digits) > 1 and count_digits[0] == "0":
        raise ValueError("trailer count has a leading zero")
    if cursor >= len(stream) or stream[cursor] != ";":
        raise ValueError("trailer is not terminated")
    cursor += 1
    if cursor != len(stream):
        raise ValueError("trailing garbage after the trailer")
    if int(count_digits) != len(frames):
        raise ValueError("trailer count does not match the frames")
    return frames
