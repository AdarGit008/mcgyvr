export function soakRun(readings: number[], floor: number): number {
  let best = 0;
  let run = 0;
  for (const reading of readings) {
    run = reading >= floor ? run + 1 : 0;
    if (run > best) {
      best = run;
    }
  }
  return best;
}
