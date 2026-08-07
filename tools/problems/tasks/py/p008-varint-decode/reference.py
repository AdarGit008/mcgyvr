def decode_varints(data: list) -> list[int]:
    if not isinstance(data, list):
        raise ValueError("decode_varints expects a list of byte values")
    values = []
    value = 0
    shift = 0
    length = 0
    for byte in data:
        if isinstance(byte, bool) or not isinstance(byte, int) or not 0 <= byte <= 255:
            raise ValueError("byte values must be integers in 0..255")
        value += (byte & 0x7F) << shift
        shift += 7
        length += 1
        if byte < 128:
            if length > 1 and byte == 0:
                raise ValueError("overlong varint encoding")
            values.append(value)
            value = 0
            shift = 0
            length = 0
    if length > 0:
        raise ValueError("truncated varint")
    return values
