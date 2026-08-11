export function diffCount(left: number[], right: number[]): number {
  let differences = Math.abs(left.length - right.length);
  const shared = Math.min(left.length, right.length);
  for (let i = 0; i < shared; i += 1) {
    if (left[i] !== right[i]) {
      differences += 1;
    }
  }
  return differences;
}
