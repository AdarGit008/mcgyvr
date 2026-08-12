"""Apply a keep/drop/add edit script to a document with context checks."""


def apply_edit_script(doc, script):
    """Rebuild the document, verifying every keep and drop against it."""
    if not isinstance(doc, str):
        raise ValueError("apply_edit_script expects a string document")
    if not isinstance(script, list):
        raise ValueError("apply_edit_script expects a list of edits")
    out = []
    cursor = 0
    for pair in script:
        if not isinstance(pair, list) or len(pair) != 2:
            raise ValueError("each edit is a [tag, text] pair")
        tag, text = pair
        if not isinstance(text, str) or not text:
            raise ValueError("edit text must be a non-empty string")
        if tag == "add":
            out.append(text)
            continue
        if tag not in ("keep", "drop"):
            raise ValueError(f"unknown edit tag: {tag!r}")
        end = cursor + len(text)
        if end > len(doc):
            raise ValueError("edit runs past the end of the document")
        piece = doc[cursor:end]
        if piece != text:
            raise ValueError("edit text does not match the document at the cursor")
        if tag == "keep":
            out.append(piece)
        cursor = end
    if cursor != len(doc):
        raise ValueError("the script leaves document characters unconsumed")
    return "".join(out)
