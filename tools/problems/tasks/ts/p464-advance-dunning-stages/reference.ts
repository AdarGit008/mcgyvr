type Span = { from: number; to: number };

type Account = {
  due: number;
  cents: number;
  paid: number;
  lastPaid: number;
  spans: Span[];
  open: number;
  frozen: boolean;
};

function whole(value: unknown): boolean {
  return typeof value === "number" && Number.isInteger(value);
}

function mapping(value: unknown): boolean {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function stageFor(age: number): string {
  if (age <= 0) return "current";
  if (age <= 14) return "reminder";
  if (age <= 29) return "notice";
  if (age <= 59) return "final";
  return "collections";
}

export function advanceDunningStages(
  invoices: Record<string, unknown>[],
  events: Record<string, unknown>[],
  reportDay: number,
): Record<string, unknown>[] {
  if (!Array.isArray(invoices) || !Array.isArray(events)) {
    throw new Error("advanceDunningStages expects two lists");
  }
  if (!whole(reportDay) || reportDay < 0) {
    throw new Error("the reporting day is not whole or falls below nought");
  }

  const book = new Map<string, Account>();
  for (const invoice of invoices) {
    if (!mapping(invoice)) {
      throw new Error("an invoice is not a mapping");
    }
    if (Object.keys(invoice).sort().join(",") !== "cents,due,id") {
      throw new Error("an invoice carries exactly id, due and cents");
    }
    const id = invoice["id"];
    if (typeof id !== "string" || id.length === 0) {
      throw new Error("an invoice id is not a non-empty string");
    }
    if (book.has(id)) {
      throw new Error("two invoices share an id");
    }
    const due = invoice["due"];
    const cents = invoice["cents"];
    if (!whole(due) || Number(due) < 0) {
      throw new Error("a due day is not whole or falls below nought");
    }
    if (!whole(cents) || Number(cents) < 1) {
      throw new Error("an invoice's cents are not whole or fall below one");
    }
    book.set(id, {
      due: Number(due),
      cents: Number(cents),
      paid: 0,
      lastPaid: -1,
      spans: [],
      open: -1,
      frozen: false,
    });
  }

  let clock = 0;
  let started = false;
  for (const event of events) {
    if (!mapping(event)) {
      throw new Error("an event is not a mapping");
    }
    const kind = event["kind"];
    if (kind !== "payment" && kind !== "dispute" && kind !== "release") {
      throw new Error("an event's kind is outside payment, dispute and release");
    }
    const wanted =
      kind === "payment" ? "cents,day,invoice,kind" : "day,invoice,kind";
    if (Object.keys(event).sort().join(",") !== wanted) {
      throw new Error("an event's keys are not the ones its kind calls for");
    }
    const day = event["day"];
    if (!whole(day) || Number(day) < 0) {
      throw new Error("an event day is not whole or falls below nought");
    }
    if (started && Number(day) < clock) {
      throw new Error("an event day steps backwards");
    }
    if (Number(day) > reportDay) {
      throw new Error("an event day runs past the reporting day");
    }
    clock = Number(day);
    started = true;
    const named = event["invoice"];
    if (typeof named !== "string" || !book.has(named)) {
      throw new Error("an event names an invoice the book does not hold");
    }
    const account = book.get(named);
    if (account === undefined) {
      throw new Error("an event names an invoice the book does not hold");
    }

    if (kind === "payment") {
      const cents = event["cents"];
      if (!whole(cents) || Number(cents) < 1) {
        throw new Error("a payment's cents are not whole or fall below one");
      }
      account.paid += Number(cents);
      account.lastPaid = clock;
      continue;
    }
    if (kind === "dispute") {
      if (account.frozen) {
        throw new Error("an invoice is disputed while already frozen");
      }
      account.frozen = true;
      account.open = clock;
      continue;
    }
    if (!account.frozen) {
      throw new Error("an invoice is released while it is not frozen");
    }
    account.frozen = false;
    account.spans.push({ from: account.open, to: clock });
  }

  const rows: Record<string, unknown>[] = [];
  for (const id of [...book.keys()].sort()) {
    const account = book.get(id);
    if (account === undefined) {
      continue;
    }
    const owed = Math.max(0, account.cents - account.paid);
    if (owed === 0) {
      rows.push({ id, stage: "settled", owed: 0 });
      continue;
    }
    const anchor = Math.max(account.due, account.lastPaid);
    const spans = account.spans.slice();
    if (account.frozen) {
      spans.push({ from: account.open, to: reportDay });
    }
    let held = 0;
    for (const span of spans) {
      const start = Math.max(span.from, anchor);
      const end = Math.min(span.to, reportDay);
      if (end > start) {
        held += end - start;
      }
    }
    rows.push({ id, stage: stageFor(reportDay - anchor - held), owed });
  }
  return rows;
}
