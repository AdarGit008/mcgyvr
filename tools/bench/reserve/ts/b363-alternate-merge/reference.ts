export function alternateMerge(left: string[], right: string[]): string[] {
  const merged: string[] = [];
  const longest = Math.max(left.length, right.length);
  for (let i = 0; i < longest; i += 1) {
    if (i < left.length) {
      merged.push(left[i]);
    }
    if (i < right.length) {
      merged.push(right[i]);
    }
  }
  return merged;
}
