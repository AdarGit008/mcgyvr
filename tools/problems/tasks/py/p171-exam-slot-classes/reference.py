def exam_slot_classes(conflicts: list[list[int]]) -> list[list[int]]:
    if not isinstance(conflicts, list) or not conflicts:
        raise ValueError("there must be at least one exam")
    total = len(conflicts)
    for exam, shared in enumerate(conflicts):
        if not isinstance(shared, list):
            raise ValueError("each exam needs a list of shared exams")
        seen = set()
        for other in shared:
            if isinstance(other, bool) or not isinstance(other, int):
                raise ValueError("a shared exam must be named by number")
            if other < 0 or other >= total:
                raise ValueError("that exam does not exist")
            if other == exam:
                raise ValueError("an exam cannot share a student with itself")
            if other in seen:
                raise ValueError("the same exam is named twice")
            seen.add(other)
            if exam not in conflicts[other]:
                raise ValueError("only one of the pair admits the sharing")

    order = sorted(range(total), key=lambda exam: (-len(conflicts[exam]), exam))
    sitting = [-1] * total
    opened = 0
    for exam in order:
        taken = {sitting[other] for other in conflicts[exam] if sitting[other] >= 0}
        pick = 0
        while pick in taken:
            pick += 1
        sitting[exam] = pick
        opened = max(opened, pick + 1)

    rows: list[list[int]] = [[] for _ in range(opened)]
    for exam in range(total):
        rows[sitting[exam]].append(exam)
    return rows
