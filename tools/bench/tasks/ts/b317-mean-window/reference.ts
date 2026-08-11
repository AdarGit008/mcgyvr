export function meanWindow(readings: number[], size: number): number[] {
  const means: number[] = [];
  for (let i = 0; i + size <= readings.length; i += 1) {
    let total = 0;
    for (let j = i; j < i + size; j += 1) {
      total += readings[j];
    }
    means.push(Math.floor(total / size));
  }
  return means;
}
