/** The total of the entries up to and including a position. */
export function runningTo(values: number[], upto: number): number {
  if (upto < 0) {
    return 0;
  }
  let total = 0;
  for (let i = 0; i <= upto && i < values.length; i += 1) {
    total += values[i];
  }
  return total;
}
