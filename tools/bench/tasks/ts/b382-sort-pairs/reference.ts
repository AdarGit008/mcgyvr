export function fieldOf(
  record: Record<string, number>,
  field: string,
): number {
  if (!(field in record)) {
    throw new Error("the record lacks that field");
  }
  return record[field];
}

export function sortPairs(
  records: Record<string, number>[],
  field: string,
): Record<string, number>[] {
  const ordered = [...records];
  ordered.sort((a, b) => fieldOf(a, field) - fieldOf(b, field));
  return ordered;
}
