export function shiftBack(text: string, places: number): string {
  const alphabet = "abcdefghijklmnopqrstuvwxyz";
  let out = "";
  for (const ch of text) {
    const at = alphabet.indexOf(ch);
    if (at === -1) {
      out += ch;
    } else {
      out += alphabet[((at - places) % 26 + 26) % 26];
    }
  }
  return out;
}
