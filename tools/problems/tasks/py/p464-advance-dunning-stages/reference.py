def _whole(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _stage_for(age):
    if age <= 0:
        return "current"
    if age <= 14:
        return "reminder"
    if age <= 29:
        return "notice"
    if age <= 59:
        return "final"
    return "collections"


def advance_dunning_stages(invoices: list, events: list, report_day: int) -> list:
    if not isinstance(invoices, list) or not isinstance(events, list):
        raise ValueError("advance_dunning_stages expects two lists")
    if not _whole(report_day) or report_day < 0:
        raise ValueError("the reporting day is not whole or falls below nought")

    book = {}
    for invoice in invoices:
        if not isinstance(invoice, dict):
            raise ValueError("an invoice is not a mapping")
        if sorted(invoice) != ["cents", "due", "id"]:
            raise ValueError("an invoice carries exactly id, due and cents")
        name = invoice["id"]
        if not isinstance(name, str) or not name:
            raise ValueError("an invoice id is not a non-empty string")
        if name in book:
            raise ValueError("two invoices share an id")
        due = invoice["due"]
        cents = invoice["cents"]
        if not _whole(due) or due < 0:
            raise ValueError("a due day is not whole or falls below nought")
        if not _whole(cents) or cents < 1:
            raise ValueError("an invoice's cents are not whole or fall below one")
        book[name] = {
            "due": due,
            "cents": cents,
            "paid": 0,
            "last_paid": -1,
            "spans": [],
            "open": -1,
            "frozen": False,
        }

    clock = 0
    started = False
    for event in events:
        if not isinstance(event, dict):
            raise ValueError("an event is not a mapping")
        kind = event.get("kind")
        if kind not in ("payment", "dispute", "release"):
            raise ValueError("an event's kind is outside payment, dispute and release")
        wanted = (
            ["cents", "day", "invoice", "kind"]
            if kind == "payment"
            else ["day", "invoice", "kind"]
        )
        if sorted(event) != wanted:
            raise ValueError("an event's keys are not the ones its kind calls for")
        day = event["day"]
        if not _whole(day) or day < 0:
            raise ValueError("an event day is not whole or falls below nought")
        if started and day < clock:
            raise ValueError("an event day steps backwards")
        if day > report_day:
            raise ValueError("an event day runs past the reporting day")
        clock = day
        started = True
        named = event["invoice"]
        if not isinstance(named, str) or named not in book:
            raise ValueError("an event names an invoice the book does not hold")
        account = book[named]

        if kind == "payment":
            cents = event["cents"]
            if not _whole(cents) or cents < 1:
                raise ValueError("a payment's cents are not whole or fall below one")
            account["paid"] += cents
            account["last_paid"] = clock
            continue
        if kind == "dispute":
            if account["frozen"]:
                raise ValueError("an invoice is disputed while already frozen")
            account["frozen"] = True
            account["open"] = clock
            continue
        if not account["frozen"]:
            raise ValueError("an invoice is released while it is not frozen")
        account["frozen"] = False
        account["spans"].append((account["open"], clock))

    rows = []
    for name in sorted(book):
        account = book[name]
        owed = max(0, account["cents"] - account["paid"])
        if owed == 0:
            rows.append({"id": name, "stage": "settled", "owed": 0})
            continue
        anchor = max(account["due"], account["last_paid"])
        spans = list(account["spans"])
        if account["frozen"]:
            spans.append((account["open"], report_day))
        held = 0
        for begins, ends in spans:
            start = max(begins, anchor)
            end = min(ends, report_day)
            if end > start:
                held += end - start
        rows.append(
            {
                "id": name,
                "stage": _stage_for(report_day - anchor - held),
                "owed": owed,
            }
        )
    return rows
