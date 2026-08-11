def mask_fault(mask: str) -> str:
    """Report the first fault in a viewer filter mask, or 'ok' when it is sound."""
    members = []
    open_at = -1
    i = 0
    while i < len(mask):
        at, ch = i, mask[i]
        if ch == "\\" and i + 1 == len(mask):
            return f"dangling escape at {at}"
        if ch == "\\":
            i, ch = i + 1, "\\" + mask[i + 1]
        if open_at < 0:
            if ch == "[":
                open_at, members = at, []
        elif ch == "]":
            for k in range(1, len(members) - 1):
                if members[k][0] == "-" and members[k + 1][0][-1] < members[k - 1][0][-1]:
                    return f"reversed range at {members[k - 1][1]}"
            open_at = -1
        else:
            members.append((ch, at))
        i += 1
    return f"unclosed class at {open_at}" if open_at >= 0 else "ok"
