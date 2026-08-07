type Mark = { at: number; kind: string };
type Sitting = { who: string; from: number; to: number; count: number };

const KINDS = ["hit", "reset"];

function record(value: any): boolean {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function text(value: any): boolean {
  return typeof value === "string" && value.length > 0;
}

function whole(value: any): boolean {
  return typeof value === "number" && Number.isInteger(value);
}

export function cutIdleSittings(events: any, gap: any, cap: any): Sitting[] {
  if (!Array.isArray(events)) {
    throw new Error("the events must be a list");
  }
  if (!whole(gap) || gap < 0) {
    throw new Error("gap must be a whole number of zero or more");
  }
  if (!whole(cap) || cap < 0) {
    throw new Error("cap must be a whole number of zero or more");
  }
  const byVisitor = new Map<string, Mark[]>();
  for (const event of events) {
    if (!record(event)) {
      throw new Error("an event must be a record");
    }
    for (const name of ["who", "at", "kind"]) {
      if (!Object.prototype.hasOwnProperty.call(event, name)) {
        throw new Error("an event is missing " + name);
      }
    }
    if (!text(event.who)) {
      throw new Error("who must be a non-empty string");
    }
    if (!whole(event.at)) {
      throw new Error("at must be a whole number");
    }
    if (!KINDS.includes(event.kind)) {
      throw new Error("kind must be hit or reset");
    }
    if (!byVisitor.has(event.who)) {
      byVisitor.set(event.who, []);
    }
    (byVisitor.get(event.who) as Mark[]).push({ at: event.at, kind: event.kind });
  }

  const report: Sitting[] = [];
  for (const who of [...byVisitor.keys()].sort()) {
    const marks = (byVisitor.get(who) as Mark[])
      .slice()
      .sort((left, right) => left.at - right.at);
    let open: Sitting | null = null;
    let previous = 0;
    for (const mark of marks) {
      const fresh =
        open === null ||
        mark.kind === "reset" ||
        mark.at - previous > gap ||
        mark.at - open.from > cap;
      if (fresh) {
        open = { who, from: mark.at, to: mark.at, count: 1 };
        report.push(open);
      } else {
        open.to = mark.at;
        open.count += 1;
      }
      previous = mark.at;
    }
  }
  return report;
}
