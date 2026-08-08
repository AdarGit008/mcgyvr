def replay_ring_log(capacity, policy, operations):
    if not isinstance(capacity, int) or isinstance(capacity, bool) or capacity < 1:
        raise ValueError("the capacity must be a positive whole number")
    if policy not in ("overwrite", "refuse"):
        raise ValueError("the policy must be overwrite or refuse")
    if not isinstance(operations, list):
        raise ValueError("the operations must be a list")
    seats = []
    journal = []
    lost = 0
    for operation in operations:
        if not isinstance(operation, list) or len(operation) == 0:
            raise ValueError("an operation must be a non-empty list")
        name = operation[0]
        if name == "push":
            if len(operation) != 2:
                raise ValueError("a push carries exactly one label")
            label = operation[1]
            if not isinstance(label, str) or label == "":
                raise ValueError("a label must be a non-empty string")
            if len(seats) < capacity:
                seats.append(label)
                journal.append("stored")
            elif policy == "overwrite":
                gone = seats.pop(0)
                seats.append(label)
                journal.append("evicted " + gone)
                lost += 1
            else:
                journal.append("refused")
                lost += 1
        elif name == "pop":
            if len(operation) != 1:
                raise ValueError("a pop carries nothing past its name")
            if not seats:
                journal.append("bare")
            else:
                journal.append("took " + seats.pop(0))
        elif name == "peek":
            if len(operation) != 1:
                raise ValueError("a peek carries nothing past its name")
            if not seats:
                journal.append("bare")
            else:
                journal.append("front " + seats[0])
        else:
            raise ValueError("unknown operation name")
    return {"contents": list(seats), "journal": journal, "lost": lost}
