export function timeGap(
  fromHour: number,
  fromMinute: number,
  toHour: number,
  toMinute: number,
): number {
  const start = fromHour * 60 + fromMinute;
  let end = toHour * 60 + toMinute;
  if (end <= start) {
    end += 24 * 60;
  }
  return end - start;
}
