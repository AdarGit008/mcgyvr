/** Parse one CSV line: quoted fields, doubled quotes, strict errors. */
export function parseCsvLine(line: string): string[] {
  if (typeof line !== "string") {
    throw new Error(`line must be a string, got ${typeof line}`);
  }
  const fields: string[] = [];
  let i = 0;
  while (true) {
    let field = "";
    if (line[i] === '"') {
      i += 1;
      let closed = false;
      while (i < line.length) {
        if (line[i] === '"') {
          if (line[i + 1] === '"') {
            field += '"';
            i += 2;
          } else {
            i += 1;
            closed = true;
            break;
          }
        } else {
          field += line[i];
          i += 1;
        }
      }
      if (!closed) {
        throw new Error("unterminated quoted field");
      }
      if (i < line.length && line[i] !== ",") {
        throw new Error(`unexpected character after closing quote at index ${i}`);
      }
    } else {
      while (i < line.length && line[i] !== ",") {
        if (line[i] === '"') {
          throw new Error(`quote inside unquoted field at index ${i}`);
        }
        field += line[i];
        i += 1;
      }
    }
    fields.push(field);
    if (i >= line.length) {
      break;
    }
    i += 1; // step over the comma; loop parses the next field, even if empty
  }
  return fields;
}
