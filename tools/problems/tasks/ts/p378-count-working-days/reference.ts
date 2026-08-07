const LENGTHS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
const SHAPE = /^\d{4}-\d{2}-\d{2}$/;
const SPAN_CAP = 40000;

function leaps(year: number): boolean {
  return year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
}

function stampOf(year: number, month: number, day: number): number {
  const shifted = month <= 2 ? year - 1 : year;
  const era = Math.floor(shifted / 400);
  const yearOfEra = shifted - era * 400;
  const dayOfYear =
    Math.floor((153 * (month + (month > 2 ? -3 : 9)) + 2) / 5) + day - 1;
  const dayOfEra =
    yearOfEra * 365 +
    Math.floor(yearOfEra / 4) -
    Math.floor(yearOfEra / 100) +
    dayOfYear;
  return era * 146097 + dayOfEra - 719468;
}

function readDate(text: unknown): number {
  if (typeof text !== "string" || !SHAPE.test(text)) {
    throw new Error("a date must read YYYY-MM-DD");
  }
  const year = Number(text.slice(0, 4));
  const month = Number(text.slice(5, 7));
  const day = Number(text.slice(8, 10));
  if (year < 1900 || year > 2999) {
    throw new Error("the year must lie between 1900 and 2999");
  }
  if (month < 1 || month > 12) {
    throw new Error("the month must lie between 01 and 12");
  }
  const held = month === 2 && leaps(year) ? 29 : LENGTHS[month - 1];
  if (day < 1 || day > held) {
    throw new Error("the day does not exist in its month");
  }
  return stampOf(year, month, day);
}

export function countWorkingDays(
  opening: string,
  closing: string,
  weekend: number[],
  holidays: string[],
): number {
  const first = readDate(opening);
  const last = readDate(closing);
  if (last < first) {
    throw new Error("the closing date falls before the opening one");
  }
  if (last - first + 1 > SPAN_CAP) {
    throw new Error("the span runs longer than " + SPAN_CAP + " days");
  }
  if (!Array.isArray(weekend)) {
    throw new Error("the weekend must be a list");
  }
  const closed = new Set<number>();
  for (const day of weekend) {
    if (typeof day !== "number" || !Number.isInteger(day) || day < 0 || day > 6) {
      throw new Error("a weekend day must be a whole number from 0 through 6");
    }
    if (closed.has(day)) {
      throw new Error("the weekend names a day twice");
    }
    closed.add(day);
  }
  if (closed.size === 7) {
    throw new Error("the weekend may not name all seven days");
  }
  if (!Array.isArray(holidays)) {
    throw new Error("the shut dates must be a list");
  }
  const shut = new Set<number>();
  for (const holiday of holidays) {
    const stamp = readDate(holiday);
    if (shut.has(stamp)) {
      throw new Error("a shut date is named twice");
    }
    shut.add(stamp);
  }
  let worked = 0;
  for (let stamp = first; stamp <= last; stamp++) {
    const weekday = (((stamp + 3) % 7) + 7) % 7;
    if (closed.has(weekday) || shut.has(stamp)) {
      continue;
    }
    worked += 1;
  }
  return worked;
}
