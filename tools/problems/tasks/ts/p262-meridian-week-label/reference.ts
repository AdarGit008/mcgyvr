const MONTH_DAYS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];

function isLeap(year: number): boolean {
  return (year % 4 === 0 && year % 100 !== 0) || year % 400 === 0;
}

function dayIndex(year: number, month: number, day: number): number {
  const prior = year - 1;
  let total =
    365 * prior +
    Math.floor(prior / 4) -
    Math.floor(prior / 100) +
    Math.floor(prior / 400);
  for (let m = 1; m < month; m++) {
    total += MONTH_DAYS[m - 1] + (m === 2 && isLeap(year) ? 1 : 0);
  }
  return total + day - 1;
}

// Index 0 is 0001-01-01, a Monday, so weekday 2 is Wednesday.
function weekOpening(index: number): number {
  const weekday = ((index % 7) + 7) % 7;
  return index - ((weekday - 2 + 7) % 7);
}

export function meridianWeekLabel(date: string): string {
  if (typeof date !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(date)) {
    throw new Error("date must be zero-padded YYYY-MM-DD");
  }
  const year = Number(date.slice(0, 4));
  const month = Number(date.slice(5, 7));
  const day = Number(date.slice(8, 10));
  if (year < 2 || year > 9999) {
    throw new Error("year must lie in 0002..9999");
  }
  if (month < 1 || month > 12) {
    throw new Error("month must lie in 01..12");
  }
  const held = MONTH_DAYS[month - 1] + (month === 2 && isLeap(year) ? 1 : 0);
  if (day < 1 || day > held) {
    throw new Error("the month does not hold that day");
  }
  const opening = weekOpening(dayIndex(year, month, day));
  let labelYear = year;
  let anchor = weekOpening(dayIndex(year, 1, 8));
  if (opening < anchor) {
    labelYear = year - 1;
    anchor = weekOpening(dayIndex(labelYear, 1, 8));
  }
  const week = (opening - anchor) / 7 + 1;
  return (
    String(labelYear).padStart(4, "0") + "-W" + String(week).padStart(2, "0")
  );
}
