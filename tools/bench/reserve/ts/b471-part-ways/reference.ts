export function partWays(left: string[], right: string[]): number {
  const shorter = left.length < right.length ? left.length : right.length;
  for (let i = 0; i < shorter; i += 1) {
    if (left[i] !== right[i]) {
      return i;
    }
  }
  if (left.length !== right.length) {
    return shorter;
  }
  return -1;
}
