export function keyOf(record: { name?: string; amount?: number }): string {
  return record.name ?? "";
}

export function groupSum(
  records: { name?: string; amount?: number }[],
): Record<string, number> {
  const totals: Record<string, number> = {};
  for (const record of records) {
    const group = keyOf(record);
    if (group === "") {
      continue;
    }
    totals[group] = (totals[group] ?? 0) + (record.amount ?? 0);
  }
  return totals;
}
