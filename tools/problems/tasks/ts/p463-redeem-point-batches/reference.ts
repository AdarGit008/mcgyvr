type Batch = { last: number; seq: number; left: number };

function whole(value: unknown): boolean {
  return typeof value === "number" && Number.isInteger(value);
}

export function redeemPointBatches(
  events: Record<string, unknown>[],
): { taken: number[]; lapsed: number; balance: number } {
  if (!Array.isArray(events)) {
    throw new Error("redeemPointBatches expects a list of events");
  }
  let batches: Batch[] = [];
  const taken: number[] = [];
  let lapsed = 0;
  let seq = 0;
  let clock = 0;
  let started = false;

  for (const event of events) {
    if (typeof event !== "object" || event === null || Array.isArray(event)) {
      throw new Error("an event is not a mapping");
    }
    const kind = event["kind"];
    if (kind !== "earn" && kind !== "burn") {
      throw new Error("an event's kind is outside earn and burn");
    }
    const keys = Object.keys(event).sort().join(",");
    const wanted = kind === "earn" ? "day,kind,life,points" : "day,kind,points";
    if (keys !== wanted) {
      throw new Error("an event's keys are not the ones its kind calls for");
    }
    const day = event["day"];
    if (!whole(day) || Number(day) < 0) {
      throw new Error("a day is not whole or falls below nought");
    }
    if (started && Number(day) < clock) {
      throw new Error("a day steps backwards");
    }
    clock = Number(day);
    started = true;
    const points = event["points"];
    if (!whole(points) || Number(points) < 1) {
      throw new Error("points are not whole or fall below one");
    }

    const alive: Batch[] = [];
    for (const batch of batches) {
      if (batch.last < clock) {
        lapsed += batch.left;
      } else {
        alive.push(batch);
      }
    }
    batches = alive;

    if (kind === "earn") {
      const life = event["life"];
      if (!whole(life) || Number(life) < 0) {
        throw new Error("a life is not whole or falls below nought");
      }
      batches.push({ last: clock + Number(life), seq, left: Number(points) });
      seq += 1;
      continue;
    }

    const want = Number(points);
    let held = 0;
    for (const batch of batches) {
      held += batch.left;
    }
    if (held < want) {
      taken.push(0);
      continue;
    }
    const order = batches
      .slice()
      .sort((a, b) => a.last - b.last || a.seq - b.seq);
    let need = want;
    for (const batch of order) {
      if (need === 0) {
        break;
      }
      const drawn = Math.min(batch.left, need);
      batch.left -= drawn;
      need -= drawn;
    }
    batches = batches.filter((batch) => batch.left > 0);
    taken.push(want);
  }

  let balance = 0;
  for (const batch of batches) {
    balance += batch.left;
  }
  return { taken, lapsed, balance };
}
