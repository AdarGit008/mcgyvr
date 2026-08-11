"""Parse newline-separated rows of comma-separated, optionally quoted fields."""


def parse_quoted_table(text: str) -> list:
    if not isinstance(text, str) or not text:
        raise ValueError("text must be a non-empty string")
    if "\r" in text:
        raise ValueError("carriage returns are not allowed")
    rows = []
    row = []
    pos = 0
    while True:
        field = []
        if pos < len(text) and text[pos] == '"':
            pos += 1
            closed = False
            while pos < len(text):
                if text[pos] != '"':
                    field.append(text[pos])
                    pos += 1
                elif text[pos + 1 : pos + 2] == '"':
                    field.append('"')
                    pos += 2
                else:
                    pos += 1
                    closed = True
                    break
            if not closed:
                raise ValueError("quoted field never closed")
            if pos < len(text) and text[pos] not in ",\n":
                raise ValueError("only a comma or newline may follow a closing quote")
        else:
            while pos < len(text) and text[pos] not in ",\n":
                if text[pos] == '"':
                    raise ValueError("quote inside an unquoted field")
                field.append(text[pos])
                pos += 1
        row.append("".join(field))
        if pos >= len(text):
            rows.append(row)
            break
        separator = text[pos]
        pos += 1
        if separator == "\n":
            rows.append(row)
            row = []
            if pos >= len(text):
                break
    for parsed in rows:
        if len(parsed) != len(rows[0]):
            raise ValueError("every row must carry as many fields as the first")
    return rows
