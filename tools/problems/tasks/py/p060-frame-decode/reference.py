def decode_frames(stream: list[int]) -> list[list[int]]:
    if not isinstance(stream, list):
        raise ValueError("decode_frames expects a list of bytes")
    for byte in stream:
        if not isinstance(byte, int) or isinstance(byte, bool) or not 0 <= byte <= 255:
            raise ValueError(f"not a byte: {byte!r}")
    frames: list[list[int]] = []
    i = 0
    while i < len(stream):
        if i + 2 > len(stream):
            raise ValueError("stream ends inside a header")
        length = stream[i] * 256 + stream[i + 1]
        i += 2
        if i + length + 1 > len(stream):
            raise ValueError("stream ends inside a frame")
        payload = stream[i : i + length]
        i += length
        check = 0
        for byte in payload:
            check ^= byte
        if stream[i] != check:
            raise ValueError("trailing byte disagrees with payload")
        i += 1
        frames.append(payload)
    return frames
