export function escChar(text: string, mark: string): string {
  let out = "";
  for (const ch of text) {
    if (ch === mark || ch === "^") {
      out += "^";
    }
    out += ch;
  }
  return out;
}
