export function zeroTail(value: number): number {
  if (value === 0) {
    return 1;
  }
  let left = value;
  let zeros = 0;
  while (left % 10 === 0) {
    zeros += 1;
    left = Math.floor(left / 10);
  }
  return zeros;
}
