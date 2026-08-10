"""Serialize [key, value] string pairs into one escaped line."""


def pack_entries(entries: list) -> str:
    if not isinstance(entries, list):
        raise ValueError("entries must be a list of pairs")

    def escape(text):
        out = []
        for ch in text:
            out.append("\\" + ch if ch in "\\=;" else ch)
        return "".join(out)

    seen = set()
    rendered = []
    for entry in entries:
        if not isinstance(entry, list) or len(entry) != 2:
            raise ValueError("each entry must be a [key, value] pair")
        key, value = entry
        if not isinstance(key, str) or not isinstance(value, str):
            raise ValueError("keys and values must be strings")
        if key == "":
            raise ValueError("keys must not be empty")
        if key in seen:
            raise ValueError("keys must not repeat")
        seen.add(key)
        rendered.append(escape(key) + "=" + escape(value))
    return ";".join(rendered)
