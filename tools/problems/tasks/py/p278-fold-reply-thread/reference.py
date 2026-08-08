def fold_reply_thread(messages: list[list[str]]) -> str:
    if not isinstance(messages, list) or not messages:
        raise ValueError("the batch must hold at least one message")
    texts: dict[str, str] = {}
    for message in messages:
        if not isinstance(message, list) or len(message) != 3:
            raise ValueError("a message is exactly three values")
        for field in message:
            if not isinstance(field, str):
                raise ValueError("a message field must be a string")
        identifier, _parent, text = message
        if not identifier:
            raise ValueError("a message needs an id")
        if identifier in texts:
            raise ValueError("two messages share an id")
        if "\n" in text:
            raise ValueError("a text may not carry a newline")
        texts[identifier] = text

    openers: list[str] = []
    answers: dict[str, list[str]] = {}
    for identifier, parent, _text in messages:
        if not parent:
            openers.append(identifier)
            continue
        if parent not in texts:
            raise ValueError("a parent names no message in the batch")
        answers.setdefault(parent, []).append(identifier)

    lines: list[str] = []

    def walk(identifier: str, depth: int) -> None:
        lines.append("> " * depth + identifier + " " + texts[identifier])
        for child in answers.get(identifier, []):
            walk(child, depth + 1)

    for identifier in openers:
        walk(identifier, 0)
    if len(lines) != len(messages):
        raise ValueError("the parent links run in a circle")
    return "\n".join(lines)
