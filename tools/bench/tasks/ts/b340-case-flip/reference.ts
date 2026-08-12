/** Text with the case of every letter turned over. */
export function swapCase(text: string): string {
  let out = "";
  for (const ch of text) {
    if (/^[a-z]$/.test(ch)) {
      out += ch.toUpperCase();
    } else if (/^[A-Z]$/.test(ch)) {
      out += ch.toLowerCase();
    } else {
      out += ch;
    }
  }
  return out;
}
