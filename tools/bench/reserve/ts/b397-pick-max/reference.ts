export function pickMax(
  records: Record<string, number>[],
  field: string,
): Record<string, number> {
  let best: Record<string, number> | null = null;
  for (const record of records) {
    if (!(field in record)) {
      continue;
    }
    if (best === null || record[field] > best[field]) {
      best = record;
    }
  }
  return best === null ? {} : best;
}
