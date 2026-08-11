export function upRuns(readings: number[]): number {
  let best = 0;
  let run = 0;
  for (let i = 0; i < readings.length; i += 1) {
    if (i > 0 && readings[i] > readings[i - 1]) {
      run += 1;
    } else {
      run = 1;
    }
    if (run > best) {
      best = run;
    }
  }
  return best;
}
