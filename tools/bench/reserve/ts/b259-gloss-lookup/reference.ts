export function glossFind(
  gloss: Record<string, string>,
  term: string,
): string | null {
  for (const key of Object.keys(gloss)) {
    if (key.toLowerCase() === term.toLowerCase()) {
      return gloss[key];
    }
  }
  return null;
}

export function glossTerms(gloss: Record<string, string>): string[] {
  return Object.keys(gloss).sort();
}
