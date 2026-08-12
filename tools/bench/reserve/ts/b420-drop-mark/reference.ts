/** The text with every occurrence of a marked character removed. */
export function dropMark(text: string, mark: string): string {
  let out = "";
  for (const ch of text) {
    if (ch !== mark) {
      out += ch;
    }
  }
  return out;
}
