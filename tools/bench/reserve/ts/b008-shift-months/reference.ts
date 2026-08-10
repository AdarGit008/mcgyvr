/** Calendar-date month arithmetic with day clamping. */

const MONTH_DAYS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];

function monthLength(year: number, month: number): number {
  const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  if (month === 2 && leap) {
    return 29;
  }
  return MONTH_DAYS[month - 1];
}

export function shiftMonths(
  year: number,
  month: number,
  day: number,
  shift: number,
): [number, number, number] {
  for (const value of [year, month, day, shift]) {
    if (!Number.isInteger(value)) {
      throw new Error("year, month, day and shift must be integers");
    }
  }
  if (month < 1 || month > 12) {
    throw new Error("month must be within 1..12");
  }
  if (day < 1 || day > monthLength(year, month)) {
    throw new Error("day does not exist in the starting month");
  }
  const index = year * 12 + (month - 1) + shift;
  const outYear = Math.floor(index / 12);
  const outMonth = index - outYear * 12 + 1;
  const outDay = Math.min(day, monthLength(outYear, outMonth));
  return [outYear, outMonth, outDay];
}
