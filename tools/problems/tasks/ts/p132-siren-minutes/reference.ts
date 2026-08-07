type Active = { channel: string; severity: number; raisedAt: number };

export function sirenMinutes(
  events: Array<Record<string, unknown>>,
  horizon: number,
): Array<[string, number]> {
  if (!Array.isArray(events)) {
    throw new Error("events must be a list");
  }
  if (!Number.isInteger(horizon)) {
    throw new Error("horizon must be an integer");
  }
  const active = new Map<string, Active>();
  const minutes = new Map<string, number>();
  let cursor: number | null = null;

  const credit = (upTo: number): void => {
    if (cursor === null) {
      return;
    }
    const span = upTo - cursor;
    if (span <= 0) {
      return;
    }
    const sounding = new Map<string, { id: string } & Active>();
    for (const [id, alert] of active) {
      const best = sounding.get(alert.channel);
      if (
        best === undefined ||
        alert.severity > best.severity ||
        (alert.severity === best.severity && alert.raisedAt < best.raisedAt)
      ) {
        sounding.set(alert.channel, { id, ...alert });
      }
    }
    for (const winner of sounding.values()) {
      minutes.set(winner.id, (minutes.get(winner.id) ?? 0) + span);
    }
  };

  for (const event of events) {
    if (typeof event !== "object" || event === null || Array.isArray(event)) {
      throw new Error("each event must be a record");
    }
    const at = event.at;
    const kind = event.kind;
    const id = event.id;
    if (!Number.isInteger(at)) {
      throw new Error("at must be an integer");
    }
    if (cursor !== null && (at as number) <= cursor) {
      throw new Error("event times must strictly increase");
    }
    if ((at as number) > horizon) {
      throw new Error("an event past the horizon is malformed");
    }
    if (typeof id !== "string" || id === "") {
      throw new Error("id must be a non-empty string");
    }
    credit(at as number);
    cursor = at as number;
    if (kind === "raise") {
      if (active.has(id)) {
        throw new Error("raise of an id already active");
      }
      const channel = event.channel;
      const severity = event.severity;
      if (typeof channel !== "string" || channel === "") {
        throw new Error("channel must be a non-empty string");
      }
      if (
        !Number.isInteger(severity) ||
        (severity as number) < 1 ||
        (severity as number) > 5
      ) {
        throw new Error("severity must be an integer from 1 to 5");
      }
      active.set(id, {
        channel,
        severity: severity as number,
        raisedAt: cursor,
      });
      if (!minutes.has(id)) {
        minutes.set(id, 0);
      }
    } else if (kind === "clear") {
      if (!active.has(id)) {
        throw new Error("clear of an id not active");
      }
      active.delete(id);
    } else {
      throw new Error("kind must be raise or clear");
    }
  }
  credit(horizon);
  return [...minutes.entries()]
    .sort((a, b) => (a[0] < b[0] ? -1 : 1))
    .map(([id, total]) => [id, total]);
}
