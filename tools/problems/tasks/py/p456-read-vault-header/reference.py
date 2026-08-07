MARKER = (86, 76, 84)


def read_vault_header(bytes_in: list) -> dict:
    if not isinstance(bytes_in, list):
        raise ValueError("bytes must be a list")
    for byte in bytes_in:
        if not isinstance(byte, int) or isinstance(byte, bool) or byte < 0 or byte > 255:
            raise ValueError("every byte must be a whole number from 0 through 255")
    if len(bytes_in) < 4:
        raise ValueError("the run is too short to carry the marker and the edition")
    for index, expected in enumerate(MARKER):
        if bytes_in[index] != expected:
            raise ValueError("the marker is not the one this reader knows")
    version = bytes_in[3]
    if version not in (1, 2):
        raise ValueError(f"edition {version} is not one this reader knows")
    header_length = 7 if version == 1 else 11
    if len(bytes_in) < header_length:
        raise ValueError("the run ends inside the header")
    size = bytes_in[4] * 256 + bytes_in[5]
    flags = bytes_in[6]
    if flags & ~3:
        raise ValueError("a flag this reader does not know is raised")
    stamp = 0
    if version == 2:
        stamp = ((bytes_in[7] * 256 + bytes_in[8]) * 256 + bytes_in[9]) * 256 + bytes_in[10]
    if len(bytes_in) - header_length != size:
        raise ValueError("the body is not the length the header declares")
    return {
        "version": version,
        "size": size,
        "sealed": flags & 1 == 1,
        "packed": flags & 2 == 2,
        "stamp": stamp,
    }
