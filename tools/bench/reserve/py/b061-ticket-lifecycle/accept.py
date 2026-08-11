from solution import replay_ticket

assert replay_ticket([]) == "new", "empty log leaves the ticket new"
assert replay_ticket(["triage"]) == "triaged", "triage moves a new ticket"
assert replay_ticket(["triage", "resolve"]) == "resolved", "resolve after triage"
assert replay_ticket(["triage", "resolve", "reopen"]) == "triaged", "reopen returns the ticket to triaged"
assert replay_ticket(["triage", "resolve", "reopen", "resolve"]) == "resolved", "a reopened ticket can resolve again"
assert replay_ticket(["triage", "resolve", "archive"]) == "archived", "archive closes a resolved ticket"


def rejects(events):
    try:
        replay_ticket(events)
    except ValueError:
        return True
    return False


assert rejects(["resolve"]), "resolve is not lawful for a new ticket"
assert rejects(["triage", "triage"]), "triage cannot repeat"
assert rejects(["escalate"]), "unknown event is rejected"
assert rejects(["triage", "resolve", "archive", "reopen"]), "archived is final"
print("ok")
