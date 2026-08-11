/** Move a 24-hour clock stamp by a whole number of minutes. */
export function shiftStamp(stamp: string, minutes: number): string {
  if (typeof stamp !== "string" || !/^\d{2}:\d{2}$/.test(stamp)) {
    throw new Error("a stamp reads as HH:MM");
  }
  const hour = Number(stamp.slice(0, 2));
  const minute = Number(stamp.slice(3));
  if (hour > 23 || minute > 59) {
    throw new Error("a stamp names a time of day");
  }
  if (typeof minutes !== "number" || !Number.isInteger(minutes)) {
    throw new Error("the offset counts whole minutes");
  }
  const day = 24 * 60;
  const moved = (((hour * 60 + minute + minutes) % day) + day) % day;
  const pad = (value: number): string => String(value).padStart(2, "0");
  return `${pad(Math.floor(moved / 60))}:${pad(moved % 60)}`;
}
