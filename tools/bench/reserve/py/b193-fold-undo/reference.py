"""Fold a stream of field edits into a bounded, merged undo stack."""


def fold_undo(changes: list, depth: int) -> list:
    stack = []
    for field, before, after in changes:
        top = stack[-1] if stack else None
        if top is not None and top[0] == field:
            stack.pop()
            entry = [field, top[1], after]
        else:
            entry = [field, before, after]
        if entry[1] == entry[2]:
            continue
        stack.append(entry)
        if len(stack) > depth:
            stack.pop(0)
    return stack
