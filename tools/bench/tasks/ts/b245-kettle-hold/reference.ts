export function kettleHold(readings: number[], target: number): number {
  let held = 0;
  for (let i = readings.length - 1; i >= 0; i -= 1) {
    if (readings[i] < target) {
      break;
    }
    held += 1;
  }
  return held;
}
