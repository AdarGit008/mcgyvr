export function rootDigit(value: number): number {
  let left = value;
  while (left >= 10) {
    let sum = 0;
    while (left > 0) {
      sum += left % 10;
      left = Math.floor(left / 10);
    }
    left = sum;
  }
  return left;
}
