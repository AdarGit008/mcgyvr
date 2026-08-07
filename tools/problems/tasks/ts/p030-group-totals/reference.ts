export function groupTotals(
  rows: Array<Record<string, unknown>>,
  key: string,
  field: string,
): Array<[string, number]> {
  if (!Array.isArray(rows)) {
    throw new Error("groupTotals expects a list of rows");
  }
  const totals = new Map<string, number>();
  for (const row of rows) {
    if (
      typeof row !== "object" ||
      row === null ||
      !(key in row) ||
      !(field in row)
    ) {
      throw new Error("row is missing a required property");
    }
    const label = row[key];
    const amount = row[field];
    if (typeof label !== "string") {
      throw new Error("group label must be a string");
    }
    if (!Number.isInteger(amount)) {
      throw new Error("amount must be an integer");
    }
    totals.set(label, (totals.get(label) ?? 0) + (amount as number));
  }
  return [...totals.entries()].sort(
    (a, b) => b[1] - a[1] || (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0),
  );
}
