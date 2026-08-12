export function applyOverrides(
  base: Record<string, string>,
  overrides: string[],
): Record<string, string> {
  if (!Array.isArray(overrides)) throw new Error("overrides must be a list");
  const merged = { ...base };
  for (const line of overrides) {
    if (typeof line !== "string") throw new Error("an override must be a string");
    const at = line.indexOf("=");
    if (at < 1) throw new Error("an override needs a non-empty name, an equals sign and a value");
    const name = line.slice(0, at);
    if (!(name in base)) throw new Error("unknown setting " + name);
    merged[name] = line.slice(at + 1);
  }
  return merged;
}
