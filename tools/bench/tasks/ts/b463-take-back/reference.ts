export function takeBack(values: number[], target: number): number {
  let total = 0;
  let taken = 0;
  let i = values.length - 1;
  while (i >= 0 && total < target) {
    total += values[i];
    taken += 1;
    i -= 1;
  }
  return total >= target ? taken : -1;
}
