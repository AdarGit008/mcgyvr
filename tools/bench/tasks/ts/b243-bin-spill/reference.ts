export function binSpill(
  bins: Record<string, number>,
  limit: number,
): string[] {
  return Object.keys(bins).filter((name) => bins[name] > limit);
}

export function binAdd(
  bins: Record<string, number>,
  name: string,
  count: number,
): Record<string, number> {
  return { ...bins, [name]: (bins[name] ?? 0) + count };
}
