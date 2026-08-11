def drain_frames(chunks: list, marker: str) -> dict:
    if not isinstance(marker, str) or len(marker) != 1:
        raise ValueError("marker must be a single character")
    buffer = "".join(chunks)
    frames = []
    held = ""
    at = 0
    while at < len(buffer):
        if buffer[at] != marker:
            held += buffer[at]
            at += 1
        elif buffer[at + 1 : at + 2] == marker:
            held += marker
            at += 2
        elif at + 1 == len(buffer):
            held += marker
            at += 1
        else:
            frames.append(held)
            held = ""
            at += 1
    return {"frames": frames, "pending": held}
