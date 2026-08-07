export function stripComments(source: string): string {
  if (typeof source !== "string") {
    throw new Error("input must be a string");
  }
  let out = "";
  let i = 0;
  while (i < source.length) {
    const ch = source[i];
    if (ch === '"') {
      let j = i + 1;
      let closed = false;
      while (j < source.length) {
        if (source[j] === "\\") {
          j += 2;
          continue;
        }
        if (source[j] === '"') {
          closed = true;
          j++;
          break;
        }
        j++;
      }
      if (!closed) {
        throw new Error("unterminated string literal");
      }
      out += source.slice(i, j);
      i = j;
      continue;
    }
    if (ch === "/" && source[i + 1] === "/") {
      while (i < source.length && source[i] !== "\n") {
        i++;
      }
      continue;
    }
    if (ch === "/" && source[i + 1] === "*") {
      const end = source.indexOf("*/", i + 2);
      if (end === -1) {
        throw new Error("unterminated block comment");
      }
      i = end + 2;
      continue;
    }
    out += ch;
    i++;
  }
  return out;
}
