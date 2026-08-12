export function digitCount(value: number): number {
  let left = value < 0 ? -value : value;
  if (left === 0) {
    return 1;
  }
  let digits = 0;
  while (left > 0) {
    digits += 1;
    left = Math.floor(left / 10);
  }
  return digits;
}
