const MINUTE_CAP = 10080;

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

export function overnightStallFee(
  entry: number,
  minutes: number,
  sheet: Record<string, unknown>,
): Record<string, unknown> {
  if (typeof sheet !== "object" || sheet === null || Array.isArray(sheet)) {
    throw new Error("the fee sheet must be a mapping");
  }
  const firstHour = whole(sheet.firstHour, 0, null, "firstHour");
  const laterHour = whole(sheet.laterHour, 0, null, "laterHour");
  const dayCap = whole(sheet.dayCap, 0, null, "dayCap");
  const nightFee = whole(sheet.nightFee, 0, null, "nightFee");
  const arrives = whole(entry, 0, null, "entry");
  const stood = whole(minutes, 1, MINUTE_CAP, "minutes");

  const leaves = arrives + stood - 1;
  const days: number[] = [];
  let nights = 0;
  let total = 0;
  for (
    let number = Math.floor(arrives / 1440);
    number <= Math.floor(leaves / 1440);
    number++
  ) {
    const opened = number * 1440;
    const fromMinute = Math.max(arrives, opened);
    const toMinute = Math.min(leaves, opened + 1439);
    const held = toMinute - fromMinute + 1;
    const hours = Math.floor((held + 59) / 60);
    let charge = firstHour + (hours - 1) * laterHour;
    if (charge > dayCap) {
      charge = dayCap;
    }
    if (fromMinute - opened < 300 && toMinute - opened >= 60) {
      charge += nightFee;
      nights += 1;
    }
    days.push(charge);
    total += charge;
  }
  return { days, nights, total };
}
