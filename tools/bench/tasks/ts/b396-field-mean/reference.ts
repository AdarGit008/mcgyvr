export function fieldMean(
  records: Record<string, number>[],
  field: string,
): number {
  const values: number[] = [];
  for (const record of records) {
    if (field in record) {
      values.push(record[field]);
    }
  }
  if (values.length === 0) {
    return 0;
  }
  let total = 0;
  for (const value of values) {
    total += value;
  }
  return Math.floor(total / values.length);
}
