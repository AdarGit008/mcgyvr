export function fieldOr(
  record: Record<string, string>,
  field: string,
  standIn: string,
): string {
  return field in record ? record[field] : standIn;
}

export function fieldList(
  records: Record<string, string>[],
  field: string,
  standIn: string,
): string[] {
  const out: string[] = [];
  for (const record of records) {
    out.push(fieldOr(record, field, standIn));
  }
  return out;
}
