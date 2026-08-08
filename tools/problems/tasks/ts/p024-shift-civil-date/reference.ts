function isLeap(year: number): boolean {
  return year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
}

const MONTH_DAYS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];

function monthLength(year: number, month: number): number {
  if (month === 2 && isLeap(year)) {
    return 29;
  }
  return MONTH_DAYS[month - 1];
}

function toDayNumber(y: number, m: number, d: number): number {
  const yy = m <= 2 ? y - 1 : y;
  const era = Math.floor(yy / 400);
  const yoe = yy - era * 400;
  const doy = Math.floor((153 * (m + (m > 2 ? -3 : 9)) + 2) / 5) + d - 1;
  const doe = yoe * 365 + Math.floor(yoe / 4) - Math.floor(yoe / 100) + doy;
  return era * 146097 + doe - 719468;
}

function fromDayNumber(z: number): [number, number, number] {
  z += 719468;
  const era = Math.floor(z / 146097);
  const doe = z - era * 146097;
  const yoe = Math.floor(
    (doe - Math.floor(doe / 1460) + Math.floor(doe / 36524) - Math.floor(doe / 146096)) /
      365,
  );
  const y = yoe + era * 400;
  const doy = doe - (365 * yoe + Math.floor(yoe / 4) - Math.floor(yoe / 100));
  const mp = Math.floor((5 * doy + 2) / 153);
  const d = doy - Math.floor((153 * mp + 2) / 5) + 1;
  const m = mp < 10 ? mp + 3 : mp - 9;
  return [m <= 2 ? y + 1 : y, m, d];
}

export function shiftCivilDate(date: string, days: number): string {
  if (typeof date !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(date)) {
    throw new Error("date must be zero-padded YYYY-MM-DD");
  }
  if (!Number.isInteger(days)) {
    throw new Error("days must be an integer");
  }
  const year = Number(date.slice(0, 4));
  const month = Number(date.slice(5, 7));
  const day = Number(date.slice(8, 10));
  if (year < 1) {
    throw new Error("year is before 0001");
  }
  if (month < 1 || month > 12) {
    throw new Error("month outside 01..12");
  }
  if (day < 1 || day > monthLength(year, month)) {
    throw new Error("day does not exist in that month");
  }
  const [y, m, d] = fromDayNumber(toDayNumber(year, month, day) + days);
  if (y < 1 || y > 9999) {
    throw new Error("result leaves years 0001..9999");
  }
  const pad = (value: number, width: number) => String(value).padStart(width, "0");
  return `${pad(y, 4)}-${pad(m, 2)}-${pad(d, 2)}`;
}
