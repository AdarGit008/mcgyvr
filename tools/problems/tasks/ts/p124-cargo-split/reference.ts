function lexLess(a: number[], b: number[]): boolean {
  const shorter = Math.min(a.length, b.length);
  for (let i = 0; i < shorter; i++) {
    if (a[i] !== b[i]) {
      return a[i] < b[i];
    }
  }
  return a.length < b.length;
}

export function splitCargo(weights: number[]): number[] {
  if (weights.length === 0) {
    throw new Error("empty manifest");
  }
  for (const w of weights) {
    if (!Number.isInteger(w) || w < 1) {
      throw new Error("weights must be positive integers");
    }
  }
  const n = weights.length;
  const total = weights.reduce((a, b) => a + b, 0);
  let best: number[] | null = null;
  let bestDiff = Infinity;
  for (let mask = 1; mask < 1 << n; mask += 2) {
    let sum = 0;
    const picked: number[] = [];
    for (let i = 0; i < n; i++) {
      if (mask & (1 << i)) {
        sum += weights[i];
        picked.push(i);
      }
    }
    const diff = Math.abs(total - 2 * sum);
    const better =
      best === null ||
      diff < bestDiff ||
      (diff === bestDiff &&
        (picked.length < best.length ||
          (picked.length === best.length && lexLess(picked, best))));
    if (better) {
      best = picked;
      bestDiff = diff;
    }
  }
  return best as number[];
}
