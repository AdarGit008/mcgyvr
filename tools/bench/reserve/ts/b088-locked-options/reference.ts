/** The options a tool runs with, settled from defaults, file and flags. */
export function settleOptions(
  defaults: Record<string, string>,
  fileValues: Record<string, string>,
  flagValues: Record<string, string>,
  locked: string[],
): Record<string, string> {
  if (!Array.isArray(locked) || locked.some((key) => typeof key !== "string")) {
    throw new Error("locked must be a list of strings");
  }
  for (const source of [defaults, fileValues, flagValues]) {
    if (typeof source !== "object" || source === null || Array.isArray(source)) {
      throw new Error("each source must be a flat mapping");
    }
    for (const value of Object.values(source)) {
      if (typeof value !== "string") {
        throw new Error("option values must be strings");
      }
    }
  }
  const settled: Record<string, string> = {};
  for (const [key, value] of Object.entries(defaults)) {
    settled[key] = value;
  }
  for (const [key, value] of Object.entries(fileValues)) {
    settled[key] = value;
  }
  for (const [key, value] of Object.entries(flagValues)) {
    if (locked.includes(key)) {
      throw new Error("locked key cannot be set by a flag: " + key);
    }
    settled[key] = value;
  }
  return settled;
}
