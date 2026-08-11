/** The smallest difference between any two values. */
export function minGap(values: number[]): number {
  if (values.length < 2) {
    return -1;
  }
  const ordered = [...values].sort((a, b) => a - b);
  let smallest = ordered[1] - ordered[0];
  for (let i = 1; i < ordered.length; i += 1) {
    const gap = ordered[i] - ordered[i - 1];
    if (gap < smallest) {
      smallest = gap;
    }
  }
  return smallest;
}
