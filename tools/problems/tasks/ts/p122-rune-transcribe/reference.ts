export function transcribeRunes(
  source: string,
  table: Array<[string, string]>,
): string {
  for (const [pattern] of table) {
    if (pattern === "") {
      throw new Error("empty pattern in rule table");
    }
  }
  let result = "";
  let at = 0;
  while (at < source.length) {
    let fired = false;
    for (const [pattern, output] of table) {
      if (source.startsWith(pattern, at)) {
        result += output;
        at += pattern.length;
        fired = true;
        break;
      }
    }
    if (!fired) {
      result += source[at];
      at += 1;
    }
  }
  return result;
}
