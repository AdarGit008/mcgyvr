const STAY_CAP = 20160;

function isMapping(value: unknown): boolean {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function whole(
  value: unknown,
  low: number,
  high: number | null,
  what: string,
): number {
  if (typeof value !== "number" || !Number.isInteger(value)) {
    throw new Error(what + " must be a whole number");
  }
  if (value < low || (high !== null && value > high)) {
    throw new Error(what + " lies outside its allowed range");
  }
  return value;
}

export function tieredParkingCharge(
  tariff: Record<string, unknown>,
  ticket: Record<string, unknown>,
): Record<string, unknown> {
  if (!isMapping(tariff) || !isMapping(ticket)) {
    throw new Error("the tariff and the ticket must both be mappings");
  }
  const rawTiers = tariff.tiers;
  if (!Array.isArray(rawTiers) || rawTiers.length === 0) {
    throw new Error("the tiers must be a non-empty list");
  }
  const tiers: Array<{ upTo: number | null; rate: number }> = [];
  let opens = 0;
  let previous = 0;
  for (let position = 0; position < rawTiers.length; position++) {
    const held = rawTiers[position];
    if (!isMapping(held)) {
      throw new Error("every tier must be a mapping");
    }
    const tier = held as Record<string, unknown>;
    const upTo = tier.upTo;
    if (upTo === null) {
      opens += 1;
      if (position !== rawTiers.length - 1) {
        throw new Error("the open tier must come last");
      }
    } else {
      whole(upTo, 1, null, "a tier's stated minutes");
      if ((upTo as number) <= previous) {
        throw new Error("the stated minutes must climb strictly");
      }
      previous = upTo as number;
    }
    const rate = whole(tier.rate, 0, null, "a tier's rate");
    tiers.push({ upTo: upTo === null ? null : (upTo as number), rate });
  }
  if (opens !== 1) {
    throw new Error("there must be exactly one open tier");
  }

  const rawCap = tariff.cap;
  const cap = rawCap === null ? null : whole(rawCap, 0, null, "the cap");
  const dayStart = whole(tariff.dayStart, 0, 1439, "dayStart");
  const grace = whole(tariff.grace, 0, null, "the grace");
  const entry = whole(ticket.entry, 0, null, "entry");
  const stay = whole(ticket.stay, 1, STAY_CAP, "the stay");

  if (stay <= grace) {
    return { days: [], capped: [], cents: 0 };
  }

  const leaves = entry + stay - 1;
  const first = Math.floor((entry - dayStart) / 1440);
  const last = Math.floor((leaves - dayStart) / 1440);
  const days: number[] = [];
  const capped: number[] = [];
  let total = 0;
  for (let number = first; number <= last; number++) {
    const opened = dayStart + number * 1440;
    const fromMinute = Math.max(entry, opened);
    const toMinute = Math.min(leaves, opened + 1439);
    const minutes = toMinute - fromMinute + 1;
    let charge = 0;
    let done = 0;
    for (const tier of tiers) {
      if (done >= minutes) {
        break;
      }
      const reach = tier.upTo === null ? minutes : Math.min(tier.upTo, minutes);
      const take = reach - done;
      if (take > 0) {
        charge += take * tier.rate;
        done += take;
      }
    }
    if (cap !== null && charge > cap) {
      charge = cap;
      capped.push(days.length);
    }
    days.push(charge);
    total += charge;
  }
  return { days, capped, cents: total };
}
