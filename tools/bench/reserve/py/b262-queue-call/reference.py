def queue_call(tickets: list, withdrawn: list, called: str):
    at = tickets.index(called)
    for i in range(at + 1, len(tickets)):
        if tickets[i] not in withdrawn:
            return tickets[i]
    return None
