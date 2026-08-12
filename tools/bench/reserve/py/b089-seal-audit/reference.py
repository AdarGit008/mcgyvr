def seal_of(note: str, prev: int) -> int:
    value = prev
    for ch in note:
        value = (value * 31 + ord(ch)) % 9973
    return value


def audit_chain(records: list) -> list:
    if not isinstance(records, list):
        raise ValueError("audit_chain expects a list of records")
    bad = []
    prev = 0
    for i, record in enumerate(records):
        if not isinstance(record, dict):
            raise ValueError("each record is a mapping")
        if not {"seq", "note", "seal"} <= set(record):
            raise ValueError("a record carries seq, note and seal")
        note = record["note"]
        seal = record["seal"]
        if not isinstance(note, str):
            raise ValueError("note must be a string")
        if not isinstance(seal, int) or isinstance(seal, bool):
            raise ValueError("seal must be an integer")
        if record["seq"] != i + 1:
            raise ValueError("seq must count upward from 1")
        if seal_of(note, prev) != seal:
            bad.append(record["seq"])
        prev = seal
    return bad
