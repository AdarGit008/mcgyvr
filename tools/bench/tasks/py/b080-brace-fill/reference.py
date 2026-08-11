import re


def fill_template(template, values):
    if not isinstance(template, str):
        raise ValueError("fill_template expects a string template")
    out, i = [], 0
    while i < len(template):
        if template[i] != "{":
            out.append(template[i])
            i += 1
            continue
        end = template.find("}", i + 1)
        if end == -1:
            raise ValueError("unterminated placeholder")
        name = template[i + 1:end]
        if re.fullmatch(r"[A-Za-z0-9_]+", name) is None:
            raise ValueError(f"bad placeholder name: {name!r}")
        if name not in values:
            raise ValueError(f"unknown placeholder: {name}")
        out.append(values[name])
        i = end + 1
    return "".join(out)
