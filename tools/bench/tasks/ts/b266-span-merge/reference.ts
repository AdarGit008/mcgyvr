export function spanMerge(spans: number[][]): number[][] {
  const ordered = [...spans].sort((a, b) => a[0] - b[0]);
  const merged: number[][] = [];
  for (const span of ordered) {
    const last = merged[merged.length - 1];
    if (last !== undefined && span[0] <= last[1]) {
      last[1] = Math.max(last[1], span[1]);
    } else {
      merged.push([span[0], span[1]]);
    }
  }
  return merged;
}
