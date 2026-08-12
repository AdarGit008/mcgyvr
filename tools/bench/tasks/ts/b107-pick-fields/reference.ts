export function pickFields(records: unknown, fields: unknown): unknown[][] {
  if (!Array.isArray(records)) {
    throw new Error("records must be a list");
  }
  if (!Array.isArray(fields) || fields.length === 0) {
    throw new Error("fields must be a non-empty list");
  }

  const wanted: { stem: string; optional: boolean }[] = [];
  const seen = new Set<string>();
  for (const field of fields) {
    if (typeof field !== "string") {
      throw new Error("field names must be strings");
    }
    const optional = field.endsWith("?");
    const stem = optional ? field.slice(0, -1) : field;
    if (stem.length === 0) {
      throw new Error("a field name needs at least one character");
    }
    if (seen.has(stem)) {
      throw new Error("field " + stem + " is named twice");
    }
    seen.add(stem);
    wanted.push({ stem, optional });
  }

  const rows: unknown[][] = [];
  for (const record of records) {
    if (typeof record !== "object" || record === null || Array.isArray(record)) {
      throw new Error("every record must be a mapping");
    }
    const source = record as Record<string, unknown>;
    const row: unknown[] = [];
    for (const { stem, optional } of wanted) {
      if (Object.prototype.hasOwnProperty.call(source, stem)) {
        row.push(source[stem]);
      } else if (optional) {
        row.push(null);
      } else {
        throw new Error("record is missing field " + stem);
      }
    }
    rows.push(row);
  }
  return rows;
}
