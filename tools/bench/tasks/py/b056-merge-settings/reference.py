"""Three-way merge of flat settings: base against ours and theirs, per key."""


def merge_settings(base, ours, theirs):
    for side in (base, ours, theirs):
        if not isinstance(side, dict):
            raise ValueError("each side must be a plain settings mapping")
        if any(not isinstance(value, str) for value in side.values()):
            raise ValueError("settings values must be strings")
    merged = {}
    for key in {**base, **ours, **theirs}:
        stem, own, other = base.get(key), ours.get(key), theirs.get(key)
        if own == other:
            kept = own
        elif own == stem:
            kept = other
        elif other == stem:
            kept = own
        else:
            raise ValueError("conflicting edits to " + key)
        if kept is not None:
            merged[key] = kept
    return merged
