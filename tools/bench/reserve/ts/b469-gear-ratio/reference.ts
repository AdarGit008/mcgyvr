export function gearRatio(first: number, second: number): string {
  if (second === 0) {
    throw new Error("the second count must not be nothing");
  }
  let left = first;
  let right = second;
  while (right !== 0) {
    const rest = left % right;
    left = right;
    right = rest;
  }
  const share = left === 0 ? 1 : left;
  return String(first / share) + ":" + String(second / share);
}
