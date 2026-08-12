/** Rank a firmware release as one sortable stamp. */
const FIELD = 1000;

export function stampBuild(major: number, minor: number, patch: number): number {
  for (const part of [major, minor, patch]) {
    if (typeof part !== "number" || !Number.isInteger(part)) {
      throw new Error("each component must be a whole number");
    }
    if (part < 0) {
      throw new Error("each component must not be negative");
    }
  }
  if (minor >= FIELD || patch >= FIELD) {
    throw new Error("minor and patch each fill three digits only");
  }
  return (major * FIELD + minor) * FIELD + patch;
}
