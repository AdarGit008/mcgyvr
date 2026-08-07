type Leg = { from: number; to: number; days: number; cents: number };

function isRecord(value: unknown): boolean {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function settlePlanTimeline(
  periodDays: number,
  openingCents: number,
  changes: { day: number; cents: number }[],
): { legs: Leg[]; total: number } {
  if (!Number.isInteger(periodDays) || periodDays < 1) {
    throw new Error("the period must be a whole number of one day or more");
  }
  if (!Number.isInteger(openingCents) || openingCents < 0) {
    throw new Error("the opening price must be a whole number of cents");
  }
  if (!Array.isArray(changes)) {
    throw new Error("the changes must be a list");
  }
  let previousDay = 1;
  const taken: { day: number; cents: number }[] = [];
  for (const change of changes) {
    if (!isRecord(change)) {
      throw new Error("a change must be a record");
    }
    const day = change.day;
    if (!Number.isInteger(day) || day < 2 || day > periodDays) {
      throw new Error("a change day must lie from two to the period's last day");
    }
    if (day <= previousDay) {
      throw new Error("the change days must climb strictly");
    }
    previousDay = day;
    const cents = change.cents;
    if (!Number.isInteger(cents) || cents < 0) {
      throw new Error("a change price must be a whole number of cents");
    }
    taken.push({ day, cents });
  }
  const legs: Leg[] = [];
  let total = 0;
  let pot = 0;
  let start = 1;
  let rate = openingCents;
  for (let index = 0; index <= taken.length; index++) {
    const end = index === taken.length ? periodDays : taken[index].day - 1;
    const days = end - start + 1;
    const product = rate * days;
    let cents = Math.floor(product / periodDays);
    pot += product % periodDays;
    if (pot >= periodDays) {
      cents += 1;
      pot -= periodDays;
    }
    legs.push({ from: start, to: end, days, cents });
    total += cents;
    if (index < taken.length) {
      start = taken[index].day;
      rate = taken[index].cents;
    }
  }
  return { legs, total };
}
