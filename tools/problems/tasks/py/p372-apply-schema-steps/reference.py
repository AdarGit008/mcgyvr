import re

LADDER = ["int", "long", "text"]
NAME = re.compile(r"[a-z][a-z0-9_]*")


def _read_name(value):
    if not isinstance(value, str) or NAME.fullmatch(value) is None:
        raise ValueError("a column name must be a lowercase word starting with a letter")
    return value


def _read_kind(value):
    if not isinstance(value, str) or value not in LADDER:
        raise ValueError("a kind must be one of int, long and text")
    return value


def _index_of(table, name):
    for position, held in enumerate(table):
        if held["name"] == name:
            return position
    return -1


def apply_schema_steps(columns: list, steps: list) -> list:
    if not isinstance(columns, list) or len(columns) == 0:
        raise ValueError("the table must be a non-empty list of columns")
    if not isinstance(steps, list):
        raise ValueError("the steps must be a list")
    table = []
    for entry in columns:
        if not isinstance(entry, dict):
            raise ValueError("every column must be a mapping")
        name = _read_name(entry.get("name"))
        kind = _read_kind(entry.get("kind"))
        if _index_of(table, name) != -1:
            raise ValueError("two columns share the name " + name)
        table.append({"name": name, "kind": kind})
    for step in steps:
        if not isinstance(step, dict):
            raise ValueError("every step must be a mapping")
        op = step.get("op")
        if op == "add":
            name = _read_name(step.get("name"))
            kind = _read_kind(step.get("kind"))
            if _index_of(table, name) != -1:
                raise ValueError("the name " + name + " is already carried")
            table.append({"name": name, "kind": kind})
        elif op == "drop":
            name = _read_name(step.get("name"))
            at = _index_of(table, name)
            if at == -1:
                raise ValueError("no column called " + name)
            if len(table) == 1:
                raise ValueError("the last column may not be dropped")
            table.pop(at)
        elif op == "rename":
            name = _read_name(step.get("name"))
            to = _read_name(step.get("to"))
            at = _index_of(table, name)
            if at == -1:
                raise ValueError("no column called " + name)
            if _index_of(table, to) != -1:
                raise ValueError("the name " + to + " is already carried")
            table[at] = {"name": to, "kind": table[at]["kind"]}
        elif op == "retype":
            name = _read_name(step.get("name"))
            kind = _read_kind(step.get("kind"))
            at = _index_of(table, name)
            if at == -1:
                raise ValueError("no column called " + name)
            if LADDER.index(kind) <= LADDER.index(table[at]["kind"]):
                raise ValueError("a retype must widen the kind")
            table[at] = {"name": name, "kind": kind}
        else:
            raise ValueError("an op must be one of add, drop, rename and retype")
    return table
