export function isGap(reading: number): boolean {
  return reading === -1;
}

/** Missing readings replaced by the last real one seen. */
export function fillGaps(readings: number[]): number[] {
  const filled: number[] = [];
  let last = -1;
  for (const reading of readings) {
    if (isGap(reading)) {
      filled.push(last);
    } else {
      filled.push(reading);
      last = reading;
    }
  }
  return filled;
}
