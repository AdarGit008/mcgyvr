export function flipTips(line: string): string {
  const words = line.split(" ");
  const out: string[] = [];
  for (const word of words) {
    if (word.length < 2) {
      out.push(word);
    } else {
      const opening = word[0];
      const closing = word[word.length - 1];
      out.push(closing + word.slice(1, word.length - 1) + opening);
    }
  }
  return out.join(" ");
}
