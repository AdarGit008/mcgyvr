export function cipherShift(text: string, step: number): string {
  const first = "a".charCodeAt(0);
  let out = "";
  for (const ch of text) {
    const code = ch.charCodeAt(0);
    if (code >= first && code < first + 26) {
      out += String.fromCharCode(first + ((code - first + step) % 26));
    } else {
      out += ch;
    }
  }
  return out;
}
