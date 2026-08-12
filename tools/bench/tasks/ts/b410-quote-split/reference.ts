export function inQuote(ch: string): boolean {
  return ch === '"';
}

export function quoteSplit(line: string): string[] {
  const pieces: string[] = [];
  let current = "";
  let quoted = false;
  for (const ch of line) {
    if (inQuote(ch)) {
      quoted = !quoted;
      current += ch;
    } else if (ch === "," && !quoted) {
      pieces.push(current);
      current = "";
    } else {
      current += ch;
    }
  }
  pieces.push(current);
  return pieces;
}
