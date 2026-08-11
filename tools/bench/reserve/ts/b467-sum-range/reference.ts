export function sumRange(first: number, last: number): number {
  let total = 0;
  for (let value = first; value <= last; value += 1) {
    total += value;
  }
  return total;
}
