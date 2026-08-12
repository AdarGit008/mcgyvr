export function valueKeys(
  store: Record<string, string>,
): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const key of Object.keys(store)) {
    counts[store[key]] = (counts[store[key]] ?? 0) + 1;
  }
  return counts;
}
