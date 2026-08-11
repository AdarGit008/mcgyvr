export function pairSums(readings: number[]): number[] {
  const totals: number[] = [];
  for (let i = 1; i < readings.length; i += 1) {
    totals.push(readings[i - 1] + readings[i]);
  }
  return totals;
}
