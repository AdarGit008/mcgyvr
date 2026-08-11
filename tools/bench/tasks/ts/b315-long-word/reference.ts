export function longWord(sentence: string): string {
  let best = "";
  for (const word of sentence.split(/\s+/)) {
    if (word.length > best.length) {
      best = word;
    }
  }
  return best;
}
