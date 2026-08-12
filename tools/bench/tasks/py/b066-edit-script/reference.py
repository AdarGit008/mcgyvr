def apply_edit_script(original, script):
    if not isinstance(original, str):
        raise ValueError("apply_edit_script expects a string original")
    cursor, output = 0, []
    for name, arg in script:
        if name == "insert":
            if not isinstance(arg, str) or not arg:
                raise ValueError("insert text must be a non-empty string")
            output.append(arg)
            continue
        if name not in ("copy", "skip"):
            raise ValueError("unknown op: " + repr(name))
        if isinstance(arg, bool) or not isinstance(arg, int) or arg < 1:
            raise ValueError("count must be a positive integer")
        if cursor + arg > len(original):
            raise ValueError("op reads past the end of the original")
        if name == "copy":
            output.append(original[cursor:cursor + arg])
        cursor += arg
    if cursor != len(original):
        raise ValueError("script must consume the original exactly")
    return "".join(output)
