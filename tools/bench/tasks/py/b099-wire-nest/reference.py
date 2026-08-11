def wire_text(text: str) -> str:
    if not isinstance(text, str):
        raise ValueError("wire_text expects a string")
    if "\n" in text:
        raise ValueError("a wire text cannot hold a newline")
    return "s" + str(len(text)) + ":" + text


def wire_value(value) -> str:
    if isinstance(value, str):
        return wire_text(value)
    if isinstance(value, bool):
        raise ValueError("a boolean is not a wire value")
    if isinstance(value, float):
        raise ValueError("only whole numbers go on the wire")
    if isinstance(value, int):
        return "n" + str(value) + ";"
    if isinstance(value, list):
        rendered = "["
        for item in value:
            rendered += wire_value(item)
        return rendered + "]"
    raise ValueError("unsupported wire value")
