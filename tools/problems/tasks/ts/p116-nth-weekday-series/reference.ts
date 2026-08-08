const OFFSETS = [0, 3, 2, 5, 0, 3, 5, 1, 4, 6, 2, 4];

function isLeap(year: number): boolean {
  return (year % 4 === 0 && year % 100 !== 0) || year % 400 === 0;
}

function daysInMonth(year: number, month: number): number {
  const lengths = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  if (month === 2 && isLeap(year)) {
    return 29;
  }
  return lengths[month - 1];
}

function mondayIndex(year: number, month: number, day: number): number {
  let y = year;
  if (month < 3) {
    y -= 1;
  }
  const sunday0 =
    (y +
      Math.floor(y / 4) -
      Math.floor(y / 100) +
      Math.floor(y / 400) +
      OFFSETS[month - 1] +
      day) %
    7;
  return (sunday0 + 6) % 7;
}

export function expandNthWeekday(
  ordinal: number,
  weekday: number,
  start: string,
  months: number
): string[] {
  if (!Number.isInteger(ordinal) || ordinal === 0 || ordinal < -1 || ordinal > 5) {
    throw new Error("ordinal must be -1 or 1..5");
  }
  if (!Number.isInteger(weekday) || weekday < 0 || weekday > 6) {
    throw new Error("weekday must be 0..6");
  }
  if (typeof start !== "string" || !/^\d{4}-\d{2}$/.test(start)) {
    throw new Error("start must be zero-padded YYYY-MM");
  }
  let year = Number(start.slice(0, 4));
  let month = Number(start.slice(5, 7));
  if (year < 1 || month < 1 || month > 12) {
    throw new Error("start must name a real month in 0001..9999");
  }
  if (!Number.isInteger(months) || months < 1 || months > 240) {
    throw new Error("months must be a positive integer of at most 240");
  }

  const dates: string[] = [];
  for (let step = 0; step < months; step++) {
    if (year > 9999) {
      throw new Error("span runs past year 9999");
    }
    const length = daysInMonth(year, month);
    const opening = mondayIndex(year, month, 1);
    const first = 1 + ((weekday - opening + 7) % 7);
    let day: number;
    if (ordinal === -1) {
      day = first + 7 * Math.floor((length - first) / 7);
    } else {
      day = first + 7 * (ordinal - 1);
    }
    if (day <= length) {
      const y = String(year).padStart(4, "0");
      const m = String(month).padStart(2, "0");
      const d = String(day).padStart(2, "0");
      dates.push(y + "-" + m + "-" + d);
    }
    month += 1;
    if (month === 13) {
      month = 1;
      year += 1;
    }
  }
  return dates;
}
