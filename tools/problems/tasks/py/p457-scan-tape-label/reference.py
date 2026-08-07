def scan_tape_label(bytes_in: list) -> dict:
    if not isinstance(bytes_in, list):
        raise ValueError("bytes must be a list")
    for byte in bytes_in:
        if not isinstance(byte, int) or isinstance(byte, bool) or byte < 0 or byte > 255:
            raise ValueError("every byte must be a whole number from 0 through 255")
    if len(bytes_in) < 5:
        raise ValueError("the run is too short for the fixed part of the label")
    if bytes_in[0] != 212 or bytes_in[1] != 79:
        raise ValueError("the two opening bytes are not this label's marker")
    major = bytes_in[2]
    if major not in (1, 2):
        raise ValueError(f"major {major} is not a shape this reader knows")
    minor = bytes_in[3]
    if minor < 1:
        raise ValueError("the record width must be at least one byte")
    records = bytes_in[4]

    header_length = 5
    extras: list[list[int]] = []
    if major == 2:
        if len(bytes_in) < 6:
            raise ValueError("the run ends before the extra count")
        count = bytes_in[5]
        header_length = 6 + 3 * count
        if len(bytes_in) < header_length:
            raise ValueError("the run ends inside the extra table")
        last = -1
        for index in range(count):
            at = 6 + 3 * index
            kind = bytes_in[at]
            if kind <= last:
                raise ValueError("the extra table is not in rising order of kind")
            last = kind
            extras.append([kind, bytes_in[at + 1] * 256 + bytes_in[at + 2]])

    if len(bytes_in) - header_length != records * minor:
        raise ValueError("what follows the label is not the run of records it promises")
    return {"major": major, "minor": minor, "records": records, "extras": extras}
