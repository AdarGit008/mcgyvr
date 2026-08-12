export function indexMap(labels: string[]): Record<string, number[]> {
  const found: Record<string, number[]> = {};
  for (let i = 0; i < labels.length; i += 1) {
    if (!(labels[i] in found)) {
      found[labels[i]] = [];
    }
    found[labels[i]].push(i);
  }
  return found;
}
