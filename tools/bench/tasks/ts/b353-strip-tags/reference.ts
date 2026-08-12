export function stripTags(line: string): string {
  let out = "";
  let inside = false;
  for (const ch of line) {
    if (ch === "<") {
      inside = true;
    } else if (ch === ">") {
      inside = false;
    } else if (!inside) {
      out += ch;
    }
  }
  return out;
}
