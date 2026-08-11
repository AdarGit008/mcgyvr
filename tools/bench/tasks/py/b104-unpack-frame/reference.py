def unpack_frame(data):
    if not isinstance(data, list):
        raise ValueError("data must be a list")
    for byte in data:
        if isinstance(byte, bool) or not isinstance(byte, int):
            raise ValueError("bytes must be integers 0..255")
        if byte < 0 or byte > 255:
            raise ValueError("bytes must be integers 0..255")
    at = 0

    def take_varint():
        nonlocal at
        value = 0
        place = 1
        length = 0
        while True:
            if at >= len(data):
                raise ValueError("the frame ends inside a varint")
            byte = data[at]
            at += 1
            length += 1
            if length > 5:
                raise ValueError("a varint holds at most five bytes")
            group = byte & 127
            if byte >= 128:
                value += group * place
                place *= 128
                continue
            if length > 1 and group == 0:
                raise ValueError("a varint must not waste its final byte")
            return value + group * place

    declared = take_varint()
    readings = [take_varint() for _ in range(declared)]
    if at > len(data) - 1:
        raise ValueError("the frame ends before its trailer")
    if at < len(data) - 1:
        raise ValueError("bytes left over after the trailer")
    if data[at] != sum(data[:-1]) % 256:
        raise ValueError("the trailer does not equal the byte sum")
    return readings
