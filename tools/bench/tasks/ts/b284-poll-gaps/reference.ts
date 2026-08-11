export function pollGaps(minutes: number[]): number[] {
  if (minutes.length < 2) {
    return [];
  }
  const ran = new Set(minutes);
  const missing: number[] = [];
  const last = minutes[minutes.length - 1];
  for (let minute = minutes[0]; minute < last; minute += 1) {
    if (!ran.has(minute)) {
      missing.push(minute);
    }
  }
  return missing;
}
