/** Tidy a sign-out sheet: collapse spacing, drop repeats, keep first spellings. */
export function cleanRoster(names: string[]): string[] {
  if (!Array.isArray(names)) throw new Error("cleanRoster expects a list of names");
  const seen = new Set<string>();
  const kept: string[] = [];
  for (const raw of names) {
    if (typeof raw !== "string") throw new Error("every entry must be a string");
    const name = raw.trim().split(/\s+/).join(" ");
    if (name === "") throw new Error("an entry may not be blank");
    if (!seen.has(name.toLowerCase())) {
      seen.add(name.toLowerCase());
      kept.push(name);
    }
  }
  return kept;
}
