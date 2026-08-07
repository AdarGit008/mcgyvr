const SHAPE = /^[a-z][a-z0-9]*$/;
const NAKED = /^[A-Za-z0-9.-]+$/;

export function writeTagMarks(label: string, fields: string[][]): string {
  if (typeof label !== "string" || !SHAPE.test(label)) {
    throw new Error("the label breaks its shape");
  }
  if (!Array.isArray(fields)) {
    throw new Error("the fields must be a list");
  }
  const arrived = new Set<string>();
  let out = "<" + label;
  for (const entry of fields) {
    if (!Array.isArray(entry) || entry.length !== 2) {
      throw new Error("every field must be a list of exactly two");
    }
    const key = entry[0];
    const text = entry[1];
    if (typeof key !== "string" || !SHAPE.test(key)) {
      throw new Error("a key breaks its shape");
    }
    if (typeof text !== "string") {
      throw new Error("a text must be a string");
    }
    if (arrived.has(key)) {
      throw new Error("the key " + key + " arrives twice");
    }
    arrived.add(key);
    out += " " + key;
    if (text.length === 0) {
      continue;
    }
    if (NAKED.test(text)) {
      out += "=" + text;
      continue;
    }
    const fence = text.includes('"') && !text.includes("'") ? "'" : '"';
    let body = "";
    for (const ch of text) {
      if (ch === "\\" || ch === fence) {
        body += "\\";
      }
      body += ch;
    }
    out += "=" + fence + body + fence;
  }
  return out + ">";
}
