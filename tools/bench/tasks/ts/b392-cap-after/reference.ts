export function capAfter(passage: string): string {
  let out = "";
  let fresh = true;
  for (const ch of passage) {
    if (fresh && /^[a-zA-Z]$/.test(ch)) {
      out += ch.toUpperCase();
      fresh = false;
    } else {
      out += ch;
    }
    if (ch === ".") {
      fresh = true;
    }
  }
  return out;
}
