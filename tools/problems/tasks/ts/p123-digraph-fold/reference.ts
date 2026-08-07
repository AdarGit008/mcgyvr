export function foldDigraphs(
  text: string,
  table: Array<[string, string]>,
): string {
  for (const [pattern] of table) {
    if (pattern === "") {
      throw new Error("empty pattern");
    }
  }
  let result = "";
  let at = 0;
  while (at < text.length) {
    let bestPattern = "";
    let bestOutput = "";
    for (const [pattern, output] of table) {
      if (pattern.length > bestPattern.length && text.startsWith(pattern, at)) {
        bestPattern = pattern;
        bestOutput = output;
      }
    }
    if (bestPattern === "") {
      result += text[at];
      at += 1;
    } else {
      result += bestOutput;
      at += bestPattern.length;
    }
  }
  return result;
}
