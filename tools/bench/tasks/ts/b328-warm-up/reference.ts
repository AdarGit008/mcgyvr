export function warmUp(readings: number[], floor: number): number[] {
  let start = 0;
  while (start < readings.length && readings[start] < floor) {
    start += 1;
  }
  return readings.slice(start);
}
