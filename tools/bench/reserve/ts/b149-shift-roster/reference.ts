export function shiftRoster(entries: [string, string][]): Record<string, string[]> {
  if (!Array.isArray(entries)) throw new Error("entries must be a list");
  const roster: Record<string, string[]> = {};
  const seen = new Set<string>();
  for (const entry of entries) {
    if (!Array.isArray(entry) || entry.length !== 2) throw new Error("each entry must be a [name, shift] pair");
    const [name, shift] = entry;
    if (typeof name !== "string" || name === "" || typeof shift !== "string" || shift === "") throw new Error("names and shifts must be non-empty strings");
    if (seen.has(name)) throw new Error("a name may appear in only one entry");
    seen.add(name);
    (roster[shift] ??= []).push(name);
  }
  for (const names of Object.values(roster)) names.sort();
  return roster;
}
