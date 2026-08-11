export function countBy(
  records: Record<string, string>[],
  field: string,
): Record<string, number> {
  if (field === "") {
    throw new Error("a field must be named");
  }
  const counts: Record<string, number> = {};
  for (const record of records) {
    if (field in record) {
      counts[record[field]] = (counts[record[field]] ?? 0) + 1;
    }
  }
  return counts;
}
