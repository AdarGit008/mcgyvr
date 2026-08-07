def _whole(value):
    return isinstance(value, int) and not isinstance(value, bool)


def commit_index(log, matches, current_term):
    if not isinstance(log, list) or not isinstance(matches, list):
        raise ValueError("the log and the copied numbers must both be lists")
    if not _whole(current_term) or current_term < 1:
        raise ValueError("the current term must be a whole number of one or more")
    previous = 0
    for term in log:
        if not _whole(term) or term < 1:
            raise ValueError("a term must be a whole number of one or more")
        if term < previous:
            raise ValueError("terms never fall as the log grows")
        if term > current_term:
            raise ValueError("no entry may be stamped above the current term")
        previous = term
    for copied in matches:
        if not _whole(copied) or copied < 0 or copied > len(log):
            raise ValueError("a copied number must lie between zero and the log length")
    quorum = (len(matches) + 1) // 2 + 1
    commit = 0
    for entry in range(len(log), 0, -1):
        if log[entry - 1] != current_term:
            continue
        copiers = 1 + sum(1 for copied in matches if copied >= entry)
        if copiers >= quorum:
            commit = entry
            break
    safe = commit
    for copied in matches:
        if copied < safe:
            safe = copied
    behind = [at for at, copied in enumerate(matches) if copied < commit]
    return {"commit": commit, "safe": safe, "behind": behind}
