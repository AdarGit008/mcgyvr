export function driftCheck(readings: number[], step: number): number {
  for (let i = 1; i < readings.length; i += 1) {
    if (Math.abs(readings[i] - readings[i - 1]) > step) {
      return i;
    }
  }
  return -1;
}
