/** Split one CSV line into fields, honouring quoted fields and doubled quotes. */
export function parseCsvLine(line: string): string[] {
  if (typeof line !== "string") {
    throw new Error(`line must be a string, got ${typeof line}`);
  }
  const fields: string[] = [];
  let field = "";
  let quoted = false;
  let index = 0;
  while (index < line.length) {
    const char = line[index];
    if (quoted) {
      if (char === '"') {
        if (line[index + 1] === '"') {
          field += '"';
          index += 2;
          continue;
        }
        quoted = false;
        index += 1;
        continue;
      }
      field += char;
      index += 1;
      continue;
    }
    if (char === '"' && field === "") {
      quoted = true;
      index += 1;
      continue;
    }
    if (char === ",") {
      fields.push(field);
      field = "";
      index += 1;
      continue;
    }
    field += char;
    index += 1;
  }
  if (quoted) {
    throw new Error(`unterminated quoted field in: ${line}`);
  }
  fields.push(field);
  return fields;
}
