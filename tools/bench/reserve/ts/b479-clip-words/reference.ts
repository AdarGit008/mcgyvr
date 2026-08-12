export function wordShort(word: string, width: number): string {
  if (word.length <= width) {
    return word;
  }
  return word.slice(0, width) + ".";
}

/** Every word cut to a width and joined with single spaces. */
export function clipWords(words: string[], width: number): string {
  const cut: string[] = [];
  for (const word of words) {
    cut.push(wordShort(word, width));
  }
  return cut.join(" ");
}
