export function mixCase(text: string): string {
  const out: string[] = [];
  let upper = true;
  for (const ch of text) {
    if (/^[a-z]$/.test(ch.toLowerCase())) {
      out.push(upper ? ch.toUpperCase() : ch.toLowerCase());
      upper = !upper;
    } else {
      out.push(ch);
    }
  }
  return out.join("");
}
