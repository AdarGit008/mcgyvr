/** An hour and a minute written as a clock reading. */
export function padTime(hour: number, minute: number): string {
  const h = hour < 10 ? "0" + String(hour) : String(hour);
  const m = minute < 10 ? "0" + String(minute) : String(minute);
  return h + ":" + m;
}
