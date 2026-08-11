export function foldEnds(values: number[]): number[] {
  const totals: number[] = [];
  let low = 0;
  let high = values.length - 1;
  while (low < high) {
    totals.push(values[low] + values[high]);
    low += 1;
    high -= 1;
  }
  if (low === high) {
    totals.push(values[low]);
  }
  return totals;
}
