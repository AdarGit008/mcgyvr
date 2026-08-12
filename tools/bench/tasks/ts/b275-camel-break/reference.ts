export function camelBreak(name: string): string[] {
  const words: string[] = [];
  let current = "";
  for (const letter of name) {
    if (letter !== letter.toLowerCase() && current !== "") {
      words.push(current);
      current = "";
    }
    current += letter.toLowerCase();
  }
  if (current !== "") {
    words.push(current);
  }
  return words;
}
