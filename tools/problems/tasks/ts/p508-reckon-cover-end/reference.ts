const LENGTHS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];

function leap(year: number): boolean {
  return year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
}

function monthLength(year: number, month: number): number {
  return month === 2 && leap(year) ? 29 : LENGTHS[month - 1];
}

function parse(text: unknown): [number, number, number] {
  if (typeof text !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(text)) {
    throw new Error("a date must be written as YYYY-MM-DD");
  }
  const year = Number(text.slice(0, 4));
  const month = Number(text.slice(5, 7));
  const day = Number(text.slice(8, 10));
  if (year < 1900 || year > 2999 || month < 1 || month > 12) {
    throw new Error("a date must name a real month in 1900 through 2999");
  }
  if (day < 1 || day > monthLength(year, month)) {
    throw new Error("a date must name a day that exists in its month");
  }
  return [year, month, day];
}

function toDays(year: number, month: number, day: number): number {
  const shifted = month <= 2 ? year - 1 : year;
  const era = Math.floor(shifted / 400);
  const yoe = shifted - era * 400;
  const doy = Math.floor((153 * (month + (month > 2 ? -3 : 9)) + 2) / 5) + day - 1;
  const doe = yoe * 365 + Math.floor(yoe / 4) - Math.floor(yoe / 100) + doy;
  return era * 146097 + doe - 719468;
}

function fromDays(count: number): string {
  const shifted = count + 719468;
  const era = Math.floor(shifted / 146097);
  const doe = shifted - era * 146097;
  const yoe = Math.floor((doe - Math.floor(doe / 1460) + Math.floor(doe / 36524) - Math.floor(doe / 146096)) / 365);
  const year = yoe + era * 400;
  const doy = doe - (365 * yoe + Math.floor(yoe / 4) - Math.floor(yoe / 100));
  const mp = Math.floor((5 * doy + 2) / 153);
  const day = doy - Math.floor((153 * mp + 2) / 5) + 1;
  const month = mp + (mp < 10 ? 3 : -9);
  const full = month <= 2 ? year + 1 : year;
  return (
    String(full).padStart(4, "0") +
    "-" +
    String(month).padStart(2, "0") +
    "-" +
    String(day).padStart(2, "0")
  );
}

function whole(value: unknown, low: number, high: number): boolean {
  return (
    typeof value === "number" && Number.isInteger(value) && value >= low && value <= high
  );
}

export function reckonCoverEnd(policy: Record<string, unknown>): Record<string, unknown> {
  if (policy === null || typeof policy !== "object" || Array.isArray(policy)) {
    throw new Error("the policy must be a mapping");
  }
  const [by, bm, bd] = parse(policy.bought);
  const bought = toDays(by, bm, bd);
  if (!whole(policy.months, 1, 120)) {
    throw new Error("months must be a whole number from 1 to 120");
  }
  const extensions = policy.extensions;
  if (!Array.isArray(extensions)) throw new Error("the extensions must be a list");
  let total = policy.months as number;
  for (const extra of extensions) {
    if (!whole(extra, 1, 60)) {
      throw new Error("an extension must be a whole number from 1 to 60");
    }
    total += extra as number;
  }

  const repairs = policy.repairs;
  if (!Array.isArray(repairs)) throw new Error("the repairs must be a list");
  let suspended = 0;
  let previous = -1;
  for (const repair of repairs) {
    if (repair === null || typeof repair !== "object" || Array.isArray(repair)) {
      throw new Error("a repair must be a mapping");
    }
    const [iy, im, id] = parse((repair as Record<string, unknown>).in);
    const [oy, om, od] = parse((repair as Record<string, unknown>).out);
    const opened = toDays(iy, im, id);
    const closed = toDays(oy, om, od);
    if (closed < opened) throw new Error("a repair may not close before it opens");
    if (opened < bought) throw new Error("a repair may not open before the purchase");
    if (previous >= 0 && opened <= previous) {
      throw new Error("the repairs must stand apart and in opening order");
    }
    previous = closed;
    suspended += closed - opened + 1;
  }

  const raw = bm + total;
  const year = by + Math.floor((raw - 1) / 12);
  const month = ((raw - 1) % 12) + 1;
  const day = Math.min(bd, monthLength(year, month));
  const ends = toDays(year, month, day) + suspended;

  const [cy, cm, cd] = parse(policy.claim);
  const claim = toDays(cy, cm, cd);
  let verdict = "covered";
  if (claim < bought) verdict = "early";
  else if (claim > ends) verdict = "lapsed";
  const left = verdict === "covered" ? ends - claim + 1 : 0;

  return { ends: fromDays(ends), suspended, verdict, left };
}
