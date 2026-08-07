function whole(value: unknown): boolean {
  return typeof value === "number" && Number.isInteger(value);
}

export function buildReplenishmentPlan(
  item: Record<string, unknown>,
  draws: number[],
): { orders: { week: number; units: number }[]; missed: number; closing: number } {
  if (typeof item !== "object" || item === null || Array.isArray(item)) {
    throw new Error("buildReplenishmentPlan expects an item mapping");
  }
  if (
    Object.keys(item).sort().join(",") !== "ceiling,floor,held,inbound,lead,pack"
  ) {
    throw new Error("the item's keys are not exactly the six named");
  }
  const levels: Record<string, number> = {};
  for (const field of ["held", "floor", "ceiling"]) {
    const value = item[field];
    if (!whole(value) || (value as number) < 0) {
      throw new Error("a held, floor or ceiling is not whole or falls below nought");
    }
    levels[field] = value as number;
  }
  if (levels["ceiling"] < levels["floor"]) {
    throw new Error("the ceiling falls below the floor");
  }
  const pack = item["pack"];
  if (!whole(pack) || (pack as number) < 1) {
    throw new Error("the pack is not whole or falls below one");
  }
  const lead = item["lead"];
  if (!whole(lead) || (lead as number) < 1) {
    throw new Error("the lead is not whole or falls below one");
  }
  const inbound = item["inbound"];
  if (!Array.isArray(inbound)) {
    throw new Error("the inbound is not a list");
  }
  if (!Array.isArray(draws)) {
    throw new Error("the draws are not a list");
  }

  const landings = new Map<number, number>();
  let pending = 0;
  let latest = 0;
  for (const entry of inbound) {
    if (typeof entry !== "object" || entry === null || Array.isArray(entry)) {
      throw new Error("an inbound entry is not a mapping");
    }
    if (Object.keys(entry).sort().join(",") !== "units,week") {
      throw new Error("an inbound entry's keys are not exactly week and units");
    }
    const week = entry["week"];
    if (!whole(week) || (week as number) < 1) {
      throw new Error("an inbound week is not whole or falls below one");
    }
    if ((week as number) <= latest) {
      throw new Error("the inbound weeks do not climb strictly");
    }
    latest = week as number;
    const units = entry["units"];
    if (!whole(units) || (units as number) < 1) {
      throw new Error("an inbound units is not whole or falls below one");
    }
    landings.set(week as number, (landings.get(week as number) ?? 0) + (units as number));
    pending += units as number;
  }

  let depot = levels["held"];
  let missed = 0;
  const orders: { week: number; units: number }[] = [];
  for (let week = 1; week <= draws.length; week++) {
    const draw = draws[week - 1];
    if (!whole(draw) || draw < 0) {
      throw new Error("a draw is not whole or falls below nought");
    }
    const landed = landings.get(week) ?? 0;
    depot += landed;
    pending -= landed;
    if (draw > depot) {
      missed += draw - depot;
      depot = 0;
    } else {
      depot -= draw;
    }
    const cover = depot + pending;
    if (cover > levels["floor"]) {
      continue;
    }
    const want = levels["ceiling"] - cover;
    if (want <= 0) {
      continue;
    }
    const units =
      Math.floor((want + (pack as number) - 1) / (pack as number)) * (pack as number);
    orders.push({ week, units });
    pending += units;
    const lands = week + (lead as number);
    landings.set(lands, (landings.get(lands) ?? 0) + units);
  }

  return { orders, missed, closing: depot };
}
