export function collapseOplog(
  records: (string | number)[][]
): (string | number)[][] {
  const chosen: Record<string, (string | number)[]> = {};
  for (const record of records) {
    const kind = record[0];
    if (kind !== "set" && kind !== "drop") {
      throw new Error("unknown record kind");
    }
    const key = record[1];
    if (typeof key !== "string") {
      throw new Error("key must be a string");
    }
    if (kind === "set" && !Number.isInteger(record[2])) {
      throw new Error("value must be an integer");
    }
    chosen[key] = record;
  }
  return Object.keys(chosen)
    .sort()
    .map((key) => chosen[key]);
}
