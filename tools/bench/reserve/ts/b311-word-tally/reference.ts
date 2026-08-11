export function wordTally(sentence: string): Record<string, number> {
  const tally: Record<string, number> = {};
  for (const word of sentence.toLowerCase().split(/\s+/)) {
    if (word !== "") {
      tally[word] = (tally[word] ?? 0) + 1;
    }
  }
  return tally;
}
