export function linkFind(
  line: string,
  opens: string,
  closes: string,
): string[] {
  const found: string[] = [];
  let inside = false;
  let current = "";
  for (const ch of line) {
    if (!inside && ch === opens) {
      inside = true;
      current = "";
    } else if (inside && ch === closes) {
      inside = false;
      found.push(current);
    } else if (inside) {
      current += ch;
    }
  }
  return found;
}
