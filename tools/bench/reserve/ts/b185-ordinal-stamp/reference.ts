const WEEKDAYS = ["Saturday", "Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday"];

/** Expand a year and a day count into a dated, named log stamp. */
export function ordinalStamp(year: number, day: number): string {
  if (!Number.isInteger(year) || year < 2000 || year > 2999) {
    throw new Error("year " + year + " is outside 2000 through 2999");
  }
  const long = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  const lengths = [31, long ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  if (!Number.isInteger(day) || day < 1 || day > (long ? 366 : 365)) {
    throw new Error("day " + day + " is outside year " + year);
  }
  let month = 0;
  let left = day;
  while (left > lengths[month]) {
    left -= lengths[month];
    month += 1;
  }
  let since = day - 1;
  for (let past = 2000; past < year; past++) {
    since += past % 4 === 0 && (past % 100 !== 0 || past % 400 === 0) ? 366 : 365;
  }
  const pad = (value: number) => String(value).padStart(2, "0");
  return year + "-" + pad(month + 1) + "-" + pad(left) + " " + WEEKDAYS[since % 7];
}
