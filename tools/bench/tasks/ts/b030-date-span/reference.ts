/** How many days lie between two proleptic Gregorian calendar dates. */

const MONTH_LENGTHS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];

/** Divisible by 4, except centuries, which need divisibility by 400. */
function isLeap(year: number): boolean {
  if (year % 400 === 0) {
    return true;
  }
  if (year % 100 === 0) {
    return false;
  }
  return year % 4 === 0;
}

function monthLength(year: number, month: number): number {
  if (month === 2 && isLeap(year)) {
    return 29;
  }
  return MONTH_LENGTHS[month - 1];
}

function validateDate(date: number[]): void {
  const [year, month, day] = date;
  for (const part of date) {
    if (!Number.isInteger(part)) {
      throw new Error("date components must be integers");
    }
  }
  if (month < 1 || month > 12) {
    throw new Error("month outside 1 to 12");
  }
  if (day < 1 || day > monthLength(year, month)) {
    throw new Error("day outside its month");
  }
}

/** Whole days in all years strictly before the given year. */
function daysBeforeYear(year: number): number {
  const prior = year - 1;
  let days = prior * 365;
  days += Math.floor(prior / 4);
  days -= Math.floor(prior / 100);
  days += Math.floor(prior / 400);
  return days;
}

/** Days from the calendar epoch up to and including the given date. */
function toOrdinal(date: number[]): number {
  validateDate(date);
  const [year, month, day] = date;
  let days = daysBeforeYear(year);
  for (let m = 1; m < month; m += 1) {
    days += monthLength(year, m);
  }
  return days + day;
}

export function spanDays(start: number[], end: number[]): number {
  const origin = toOrdinal(start);
  const target = toOrdinal(end);
  if (origin > target) {
    throw new Error("start date after end date");
  }
  return target - origin;
}
