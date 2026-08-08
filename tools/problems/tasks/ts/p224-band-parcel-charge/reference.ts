function isMapping(value: unknown): boolean {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function whole(value: unknown): boolean {
  return typeof value === "number" && Number.isInteger(value);
}

export function bandParcelCharge(
  book: Record<string, unknown>,
  parcel: Record<string, unknown>,
): Record<string, unknown> {
  if (!isMapping(book)) throw new Error("the book must be a mapping");
  if (!isMapping(parcel)) throw new Error("the parcel must be a mapping");

  const zones = book.zones;
  if (!Array.isArray(zones) || zones.length === 0) {
    throw new Error("the zones must be a non-empty list");
  }
  const zoneAt = new Map<string, number>();
  for (const zone of zones) {
    if (typeof zone !== "string" || zone.length === 0) {
      throw new Error("a zone must be a non-empty name");
    }
    if (zoneAt.has(zone)) throw new Error("a zone is listed twice");
    zoneAt.set(zone, zoneAt.size);
  }

  const steps = book.steps;
  if (!Array.isArray(steps) || steps.length === 0) {
    throw new Error("the bands must be a non-empty list");
  }
  const upTo: Array<number | null> = [];
  const prices: number[][] = [];
  let previous = 0;
  for (let at = 0; at < steps.length; at++) {
    const step = steps[at];
    if (!isMapping(step)) throw new Error("a band must be a mapping");
    const edge = (step as Record<string, unknown>).upTo;
    if (edge === null) {
      if (at !== steps.length - 1) {
        throw new Error("the open band must be the last band");
      }
    } else {
      if (!whole(edge) || (edge as number) <= 0) {
        throw new Error("a stated weight must be a positive whole number");
      }
      if ((edge as number) <= previous) {
        throw new Error("the stated weights must climb strictly");
      }
      previous = edge as number;
    }
    const cents = (step as Record<string, unknown>).cents;
    if (!Array.isArray(cents) || cents.length !== zones.length) {
      throw new Error("a band prices one zone at a time");
    }
    for (const price of cents) {
      if (!whole(price) || (price as number) < 0) {
        throw new Error("a price must be a non-negative whole number");
      }
    }
    upTo.push(edge as number | null);
    prices.push(cents as number[]);
  }
  if (upTo[upTo.length - 1] !== null) {
    throw new Error("the book needs one open band");
  }

  const extras = book.extras;
  if (!Array.isArray(extras)) throw new Error("the extras must be a list");
  const marks: string[] = [];
  const markCents = new Map<string, number>();
  const markZones = new Map<string, Set<string> | null>();
  for (const extra of extras) {
    if (!isMapping(extra)) throw new Error("a charge must be a mapping");
    const mark = (extra as Record<string, unknown>).mark;
    const cents = (extra as Record<string, unknown>).cents;
    const covers = (extra as Record<string, unknown>).zones;
    if (typeof mark !== "string" || mark.length === 0) {
      throw new Error("a mark must be a non-empty name");
    }
    if (markCents.has(mark)) throw new Error("a mark is charged twice");
    if (!whole(cents) || (cents as number) < 0) {
      throw new Error("a charge must be a non-negative whole number");
    }
    let allowed: Set<string> | null = null;
    if (covers !== null) {
      if (!Array.isArray(covers)) throw new Error("a charge covers a list of zones");
      allowed = new Set<string>();
      for (const zone of covers) {
        if (typeof zone !== "string" || !zoneAt.has(zone)) {
          throw new Error("a charge names an unknown zone");
        }
        if (allowed.has(zone)) throw new Error("a charge repeats a zone");
        allowed.add(zone);
      }
    }
    marks.push(mark);
    markCents.set(mark, cents as number);
    markZones.set(mark, allowed);
  }

  const step = book.round;
  if (!whole(step) || (step as number) <= 0) {
    throw new Error("round must be a positive whole number");
  }

  const zone = parcel.zone;
  if (typeof zone !== "string" || !zoneAt.has(zone)) {
    throw new Error("the parcel names an unknown zone");
  }
  const grams = parcel.grams;
  if (!whole(grams) || (grams as number) <= 0) {
    throw new Error("grams must be a positive whole number");
  }
  const carried = parcel.marks;
  if (!Array.isArray(carried)) throw new Error("the parcel's marks must be a list");
  const onParcel = new Set<string>();
  for (const mark of carried) {
    if (typeof mark !== "string" || !markCents.has(mark)) {
      throw new Error("the parcel carries a mark the book does not name");
    }
    if (onParcel.has(mark)) throw new Error("the parcel repeats a mark");
    onParcel.add(mark);
  }

  let band = upTo.length - 1;
  for (let at = 0; at < upTo.length; at++) {
    const edge = upTo[at];
    if (edge === null || (grams as number) <= edge) {
      band = at;
      break;
    }
  }
  const base = prices[band][zoneAt.get(zone) as number];
  const applied: string[] = [];
  let extra = 0;
  for (const mark of marks) {
    if (!onParcel.has(mark)) continue;
    const allowed = markZones.get(mark) as Set<string> | null;
    if (allowed !== null && !allowed.has(zone)) continue;
    applied.push(mark);
    extra += markCents.get(mark) as number;
  }
  const sum = base + extra;
  const unit = step as number;
  const total = sum % unit === 0 ? sum : sum + (unit - (sum % unit));
  return { band, base, extra, total, applied };
}
