/** Render raw bytes as grouped lowercase hex for a debug line. */

export function hexGroups(values: number[], width: number): string {
  if (!Array.isArray(values)) {
    throw new Error("hexGroups expects a list of byte values");
  }
  if (!Number.isInteger(width) || width <= 0) {
    throw new Error("group width must be a positive integer");
  }
  const pairs: string[] = [];
  for (const value of values) {
    if (!Number.isInteger(value) || value < 0 || value > 255) {
      throw new Error("every byte must be an integer from 0 to 255");
    }
    pairs.push(value.toString(16).padStart(2, "0"));
  }
  const groups: string[] = [];
  for (let i = 0; i < pairs.length; i += width) {
    groups.push(pairs.slice(i, i + width).join(""));
  }
  return groups.join(" ");
}
