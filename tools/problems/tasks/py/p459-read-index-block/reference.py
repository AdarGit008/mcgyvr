def _allowed(byte: int) -> bool:
    return 97 <= byte <= 122 or 48 <= byte <= 57


def read_index_block(bytes_in: list) -> list:
    if not isinstance(bytes_in, list):
        raise ValueError("bytes must be a list")
    for byte in bytes_in:
        if not isinstance(byte, int) or isinstance(byte, bool) or byte < 0 or byte > 255:
            raise ValueError("every byte must be a whole number from 0 through 255")
    if not bytes_in:
        raise ValueError("the block is empty, so it does not even carry its count")

    count = bytes_in[0]
    rows: list[list] = []
    at = 1
    previous = ""
    for _ in range(count):
        if at >= len(bytes_in):
            raise ValueError("the block ends where another entry was promised")
        width = bytes_in[at]
        if width < 1:
            raise ValueError("an entry name must be at least one byte long")
        if at + 1 + width + 4 > len(bytes_in):
            raise ValueError("the block ends inside an entry")
        name = ""
        for step in range(width):
            byte = bytes_in[at + 1 + step]
            if not _allowed(byte):
                raise ValueError("an entry name may hold only small letters and digits")
            name += chr(byte)
        if name <= previous:
            raise ValueError("the entries are not in strictly rising name order")
        previous = name
        base = at + 1 + width
        rows.append(
            [name, bytes_in[base] * 256 + bytes_in[base + 1], bytes_in[base + 2] * 256 + bytes_in[base + 3]]
        )
        at = base + 4
    if at != len(bytes_in):
        raise ValueError("the block carries bytes past its last entry")
    return rows
