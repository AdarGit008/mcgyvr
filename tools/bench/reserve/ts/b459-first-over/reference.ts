/** The first reading standing above a level, or nothing at all. */
export function firstOver(readings: number[], level: number): number {
  for (const reading of readings) {
    if (reading > level) {
      return reading;
    }
  }
  return 0;
}
