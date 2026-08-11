export function midPair(values: number[]): number[] {
  if (values.length === 0) {
    return [0, 0];
  }
  const ordered = [...values].sort((a, b) => a - b);
  const half = Math.floor(ordered.length / 2);
  if (ordered.length % 2 === 1) {
    return [ordered[half], ordered[half]];
  }
  return [ordered[half - 1], ordered[half]];
}
