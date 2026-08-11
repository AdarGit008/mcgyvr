export function initialsOf(name: string): string {
  const words = name.split(/\s+/).filter((word) => word !== "");
  if (words.length === 0) {
    return "";
  }
  return words.map((word) => word[0].toUpperCase()).join(".") + ".";
}
