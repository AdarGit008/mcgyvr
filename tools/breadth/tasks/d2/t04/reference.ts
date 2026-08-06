/** Split on spaces/tabs, honoring double quotes and backslash escapes. */
export function tokenize(input: string): string[] {
  if (typeof input !== "string") {
    throw new Error(`input must be a string, got ${typeof input}`);
  }
  const tokens: string[] = [];
  let current = "";
  let building = false;
  let quoted = false;
  let i = 0;
  while (i < input.length) {
    const ch = input[i];
    if (ch === "\\") {
      if (i + 1 >= input.length) {
        throw new Error("trailing backslash with nothing to escape");
      }
      current += input[i + 1];
      building = true;
      i += 2;
    } else if (ch === '"') {
      quoted = !quoted;
      building = true;
      i += 1;
    } else if (!quoted && (ch === " " || ch === "\t")) {
      if (building) {
        tokens.push(current);
        current = "";
        building = false;
      }
      i += 1;
    } else {
      current += ch;
      building = true;
      i += 1;
    }
  }
  if (quoted) {
    throw new Error("unterminated quote");
  }
  if (building) {
    tokens.push(current);
  }
  return tokens;
}
