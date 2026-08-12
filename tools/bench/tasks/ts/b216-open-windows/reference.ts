/** Report the stretches of a clinic's day that no appointment covers. */
export function openWindows(span: string, booked: string[]): string {
  const clock = /^\d{2}:\d{2}$/;
  const minutes = (range: string): number[] => {
    const parts = range.split("-");
    if (parts.length !== 2 || !clock.test(parts[0]) || !clock.test(parts[1])) {
      throw new Error("a range must be written HH:MM-HH:MM: " + range);
    }
    return parts.map((at) => Number(at.slice(0, 2)) * 60 + Number(at.slice(3)));
  };
  const stamp = (at: number): string =>
    String(Math.floor(at / 60)).padStart(2, "0") + ":" + String(at % 60).padStart(2, "0");
  const [opening, closing] = minutes(span);
  const free: string[] = [];
  let cursor = opening;
  for (const [start, end] of booked.map(minutes).sort((a, b) => a[0] - b[0])) {
    if (start > cursor) {
      free.push(stamp(cursor) + "-" + stamp(start));
    }
    cursor = Math.max(cursor, end);
  }
  if (closing > cursor) {
    free.push(stamp(cursor) + "-" + stamp(closing));
  }
  return free.length === 0 ? "none" : free.join(", ");
}
