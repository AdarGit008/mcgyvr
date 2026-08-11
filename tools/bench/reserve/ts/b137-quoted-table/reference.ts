/** Parse newline-separated rows of comma-separated, optionally quoted fields. */

export function parseQuotedTable(text: string): string[][] {
  if (typeof text !== "string" || text.length === 0) {
    throw new Error("text must be a non-empty string");
  }
  if (text.includes("\r")) {
    throw new Error("carriage returns are not allowed");
  }
  const rows: string[][] = [];
  let row: string[] = [];
  let pos = 0;
  while (true) {
    let field = "";
    if (text[pos] === '"') {
      pos += 1;
      let closed = false;
      while (pos < text.length) {
        if (text[pos] !== '"') {
          field += text[pos];
          pos += 1;
        } else if (text[pos + 1] === '"') {
          field += '"';
          pos += 2;
        } else {
          pos += 1;
          closed = true;
          break;
        }
      }
      if (!closed) {
        throw new Error("quoted field never closed");
      }
      if (pos < text.length && text[pos] !== "," && text[pos] !== "\n") {
        throw new Error("only a comma or newline may follow a closing quote");
      }
    } else {
      while (pos < text.length && text[pos] !== "," && text[pos] !== "\n") {
        if (text[pos] === '"') {
          throw new Error("quote inside an unquoted field");
        }
        field += text[pos];
        pos += 1;
      }
    }
    row.push(field);
    if (pos >= text.length) {
      rows.push(row);
      break;
    }
    const separator = text[pos];
    pos += 1;
    if (separator === "\n") {
      rows.push(row);
      row = [];
      if (pos >= text.length) {
        break;
      }
    }
  }
  for (const parsed of rows) {
    if (parsed.length !== rows[0].length) {
      throw new Error("every row must carry as many fields as the first");
    }
  }
  return rows;
}
