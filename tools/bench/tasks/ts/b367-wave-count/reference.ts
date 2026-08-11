export function waveCount(readings: number[]): number {
  let changes = 0;
  let last = 0;
  for (let i = 1; i < readings.length; i += 1) {
    let way = 0;
    if (readings[i] > readings[i - 1]) {
      way = 1;
    } else if (readings[i] < readings[i - 1]) {
      way = -1;
    }
    if (way !== 0 && last !== 0 && way !== last) {
      changes += 1;
    }
    if (way !== 0) {
      last = way;
    }
  }
  return changes;
}
