export function spreadTabs(text: string, width: number): string {
  if (typeof text !== "string") throw new Error("text must be a string");
  if (!Number.isInteger(width) || width < 1) throw new Error("width must be a positive whole number");
  let out = "";
  let column = 0;
  for (const ch of text) {
    if (ch === "\t") {
      const pad = width - (column % width);
      out += " ".repeat(pad);
      column += pad;
    } else {
      out += ch;
      column = ch === "\n" ? 0 : column + 1;
    }
  }
  return out;
}
