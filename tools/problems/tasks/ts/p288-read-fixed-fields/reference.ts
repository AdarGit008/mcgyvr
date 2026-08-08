type Field = { name: string; start: number; width: number };

function whole(value: unknown): boolean {
  return typeof value === "number" && Number.isInteger(value);
}

export function readFixedFields(
  lines: string[],
  layout: Field[],
): Record<string, string>[] {
  if (!Array.isArray(layout) || layout.length === 0) {
    throw new Error("layout must be a non-empty list");
  }
  const names = new Set<string>();
  const claimed = new Set<number>();
  for (const field of layout) {
    if (field === null || typeof field !== "object") {
      throw new Error("a layout entry must be a record");
    }
    if (typeof field.name !== "string" || field.name.length === 0) {
      throw new Error("a field name must be a non-empty string");
    }
    if (names.has(field.name)) {
      throw new Error("field names repeat: " + field.name);
    }
    names.add(field.name);
    if (!whole(field.start) || field.start < 1) {
      throw new Error("start must be an integer of at least 1: " + field.name);
    }
    if (!whole(field.width) || field.width < 1) {
      throw new Error("width must be an integer of at least 1: " + field.name);
    }
    for (let column = field.start; column < field.start + field.width; column++) {
      if (claimed.has(column)) {
        throw new Error("two fields claim column " + String(column));
      }
      claimed.add(column);
    }
  }
  if (!Array.isArray(lines)) {
    throw new Error("lines must be a list of strings");
  }
  for (const line of lines) {
    if (typeof line !== "string") {
      throw new Error("lines must be a list of strings");
    }
    if (line.includes("\t")) {
      throw new Error("a tab cannot be measured on a column grid");
    }
  }

  const read: Record<string, string>[] = [];
  for (const line of lines) {
    const record: Record<string, string> = {};
    for (const field of layout) {
      const raw = line.slice(field.start - 1, field.start - 1 + field.width);
      const padded = raw + " ".repeat(field.width - raw.length);
      record[field.name] = padded.replace(/ +$/, "");
    }
    read.push(record);
  }
  return read;
}
