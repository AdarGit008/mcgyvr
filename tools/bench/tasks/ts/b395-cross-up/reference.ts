export function crossUp(readings: number[], level: number): number {
  let crossings = 0;
  for (let i = 1; i < readings.length; i += 1) {
    if (readings[i - 1] < level && readings[i] >= level) {
      crossings += 1;
    }
  }
  return crossings;
}
