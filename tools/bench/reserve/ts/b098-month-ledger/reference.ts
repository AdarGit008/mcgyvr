/** Per-month totals of a day-stamped worklog. */
export function monthLedger(entries: [string, number][]): [string, number, number][] {
  if (!Array.isArray(entries)) {
    throw new Error("entries must be a list");
  }
  const minutesBy: Record<string, number> = {};
  const countBy: Record<string, number> = {};
  for (const [stamp, minutes] of entries) {
    if (typeof stamp !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(stamp)) {
      throw new Error("malformed day stamp");
    }
    const month = Number(stamp.slice(5, 7));
    if (month < 1 || month > 12) {
      throw new Error("month out of range: " + stamp);
    }
    const day = Number(stamp.slice(8, 10));
    if (day < 1 || day > 31) {
      throw new Error("day out of range: " + stamp);
    }
    if (!Number.isInteger(minutes) || minutes <= 0) {
      throw new Error("minutes must be a positive integer");
    }
    const key = stamp.slice(0, 7);
    minutesBy[key] = (minutesBy[key] ?? 0) + minutes;
    countBy[key] = (countBy[key] ?? 0) + 1;
  }
  return Object.keys(minutesBy)
    .sort()
    .map((key) => [key, minutesBy[key], countBy[key]]);
}
