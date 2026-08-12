/** One total for each run of readings at or above a floor. */
export function runTotal(readings: number[], floor: number): number[] {
  const totals: number[] = [];
  let running = 0;
  let inRun = false;
  for (const reading of readings) {
    if (reading >= floor) {
      running += reading;
      inRun = true;
    } else if (inRun) {
      totals.push(running);
      running = 0;
      inRun = false;
    }
  }
  if (inRun) {
    totals.push(running);
  }
  return totals;
}
