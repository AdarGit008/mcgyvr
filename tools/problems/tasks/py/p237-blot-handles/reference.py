import re

HANDLE = re.compile(r"(?<![a-z0-9_@])@[a-z0-9_]{3,12}(?![a-z0-9_])")


def _blot_plain(part):
    def swap(found):
        seen = found.group(0)
        return "@" + seen[1] + "." * (len(seen) - 2)

    return HANDLE.sub(swap, part)


def blot_handles(message: str) -> str:
    if not isinstance(message, str):
        raise ValueError("blot_handles expects a string")
    parts = []
    index = 0
    while index < len(message):
        open_at = message.find("`", index)
        if open_at < 0:
            parts.append(_blot_plain(message[index:]))
            break
        parts.append(_blot_plain(message[index:open_at]))
        shut_at = message.find("`", open_at + 1)
        if shut_at < 0:
            parts.append(message[open_at:])
            break
        parts.append(message[open_at : shut_at + 1])
        index = shut_at + 1
    return "".join(parts)
