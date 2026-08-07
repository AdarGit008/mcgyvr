def replay_loan_desk(stock: dict, cap: int, events: list) -> list:
    if not isinstance(cap, int) or isinstance(cap, bool) or cap < 1:
        raise ValueError("bad cap")
    if not isinstance(stock, dict):
        raise ValueError("bad stock")
    free = {}
    loans = {}
    queues = {}
    for title, copies in stock.items():
        if not isinstance(copies, int) or isinstance(copies, bool) or copies < 1:
            raise ValueError("bad copy count")
        free[title] = copies
        loans[title] = {}
        queues[title] = []
    open_loans = {}
    answers = []
    for event in events:
        if not isinstance(event, (list, tuple)) or len(event) != 3:
            raise ValueError("bad event")
        action, member, title = event
        if action not in ("borrow", "return", "renew", "hold"):
            raise ValueError("unknown action")
        if title not in free:
            answers.append("no:unknown-title")
            continue
        title_loans = loans[title]
        queue = queues[title]
        if action == "borrow":
            if member in title_loans:
                answers.append("no:already-out")
            elif open_loans.get(member, 0) >= cap:
                answers.append("no:member-cap")
            elif free[title] == 0:
                answers.append("no:none-left")
            elif queue and queue[0] != member:
                answers.append("no:queued-ahead")
            else:
                if queue and queue[0] == member:
                    queue.pop(0)
                title_loans[member] = 0
                free[title] -= 1
                open_loans[member] = open_loans.get(member, 0) + 1
                answers.append("ok")
        elif action == "return":
            if member not in title_loans:
                answers.append("no:not-out")
            else:
                del title_loans[member]
                free[title] += 1
                open_loans[member] -= 1
                answers.append("ok")
        elif action == "renew":
            if member not in title_loans:
                answers.append("no:not-out")
            elif queue:
                answers.append("no:on-hold")
            elif title_loans[member] >= 2:
                answers.append("no:renew-cap")
            else:
                title_loans[member] += 1
                answers.append("ok")
        else:
            if member in title_loans:
                answers.append("no:own-loan")
            elif member in queue:
                answers.append("no:in-queue")
            elif free[title] > 0:
                answers.append("no:take-it")
            else:
                queue.append(member)
                answers.append("ok")
    return answers
