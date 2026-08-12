export function pairGap(values: number[]): number[] {
  if (values.length < 2) {
    throw new Error("need at least two values");
  }
  const sorted = [...values].sort((a, b) => a - b);
  let best = 0;
  for (let i = 1; i < sorted.length - 1; i += 1) {
    if (sorted[i + 1] - sorted[i] < sorted[best + 1] - sorted[best]) {
      best = i;
    }
  }
  return [sorted[best], sorted[best + 1]];
}
