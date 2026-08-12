export function oxfordJoin(names: string[]): string {
  if (names.length === 0) {
    return "";
  }
  if (names.length === 1) {
    return names[0];
  }
  return names.slice(0, -1).join(", ") + " and " + names[names.length - 1];
}
