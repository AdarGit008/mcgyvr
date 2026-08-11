export function maskWord(word: string): string {
  if (word.length <= 2) {
    return word;
  }
  return word[0] + ".".repeat(word.length - 2) + word[word.length - 1];
}

export function maskLine(line: string): string {
  return line
    .split(/\s+/)
    .filter((word) => word !== "")
    .map((word) => maskWord(word))
    .join(" ");
}
