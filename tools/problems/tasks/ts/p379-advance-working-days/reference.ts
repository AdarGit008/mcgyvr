const LENGTHS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
const SHAPE = /^\d{4}-\d{2}-\d{2}$/;
const MOVE_CAP = 5000;

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

function pad(value: number, width: number): string {
  let text = String(value);
  while (text.length < width) {
    text = "0" + text;
  }
  return text;
}

function spell(stamp: number): string {
  const shifted = stamp + 719468;
  const era = Math.floor(shifted / 146097);
  const dayOfEra = shifted - era * 146097;
  const yearOfEra = Math.floor(
    (dayOfEra -
      Math.floor(dayOfEra / 1460) +
      Math.floor(dayOfEra / 36524) -
      Math.floor(dayOfEra / 146096)) /
      365,
  );
  let year = yearOfEra + era * 400;
  const dayOfYear =
    dayOfEra -
    (365 * yearOfEra + Math.floor(yearOfEra / 4) - Math.floor(yearOfEra / 100));
  const marker = Math.floor((5 * dayOfYear + 2) / 153);
  const day = dayOfYear - Math.floor((153 * marker + 2) / 5) + 1;
  const month = marker < 10 ? marker + 3 : marker - 9;
  if (month <= 2) {
    year += 1;
  }
  return pad(year, 4) + "-" + pad(month, 2) + "-" + pad(day, 2);
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

const LOW = stampOf(1900, 1, 1);
const HIGH = stampOf(2999, 12, 31);

function within(stamp: number): number {
  if (stamp < LOW || stamp > HIGH) {
    throw new Error("the walk leaves the years 1900 through 2999");
  }
  return stamp;
}

export function advanceWorkingDays(
  start: string,
  count: number,
  closures: string[],
): string {
  let stamp = readDate(start);
  if (typeof count !== "number" || !Number.isInteger(count)) {
    throw new Error("the move must be a whole number");
  }
  if (count < -MOVE_CAP || count > MOVE_CAP) {
    throw new Error("the move may not pass " + MOVE_CAP + " either way");
  }
  if (!Array.isArray(closures)) {
    throw new Error("the shut days must be a list");
  }
  const shut = new Set<number>();
  for (const closure of closures) {
    const marked = readDate(closure);
    if (shut.has(marked)) {
      throw new Error("a shut day is named twice");
    }
    shut.add(marked);
  }
  const works = (at: number): boolean =>
    (((at + 3) % 7) + 7) % 7 < 5 && !shut.has(at);

  if (count === 0) {
    while (!works(stamp)) {
      stamp = within(stamp + 1);
    }
    return spell(stamp);
  }
  const step = count > 0 ? 1 : -1;
  let left = Math.abs(count);
  while (left > 0) {
    stamp = within(stamp + step);
    if (works(stamp)) {
      left -= 1;
    }
  }
  return spell(stamp);
}
