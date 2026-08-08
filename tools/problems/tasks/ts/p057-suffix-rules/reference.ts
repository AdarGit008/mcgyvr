export function applyInflections(
  word: string,
  rules: Array<[string, string]>,
): string {
  for (const [suffix, replacement] of rules) {
    if (suffix === "") {
      throw new Error("empty suffix in rule table");
    }
    if (word.endsWith(suffix)) {
      return word.slice(0, word.length - suffix.length) + replacement;
    }
  }
  return word;
}
