def line_tag(body):
    if not isinstance(body, str):
        raise ValueError("line_tag expects a string")
    return format(sum(ord(ch) for ch in body) % 256, "02x")


def check_line(line):
    if not isinstance(line, str):
        raise ValueError("check_line expects a string")
    if len(line) < 3 or line[-3] != "~":
        raise ValueError("missing tag separator")
    body = line[:-3]
    if line[-2:] != line_tag(body):
        raise ValueError("tag does not match body")
    return body
