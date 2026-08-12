/** Whether a minute of the day falls inside a window. */
export function timeIn(minute: number, opens: number, closes: number): boolean {
  if (opens <= closes) {
    return minute >= opens && minute < closes;
  }
  return minute >= opens || minute < closes;
}
