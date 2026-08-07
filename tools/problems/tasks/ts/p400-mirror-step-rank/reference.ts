export function mirrorStepRank(word: string): number {
  if (typeof word !== "string") {
    throw new Error("mirrorStepRank expects the word as text");
  }
  if (word.length === 0) {
    throw new Error("a word is never empty");
  }
  if (word.length > 30) {
    throw new Error("a word runs no longer than thirty marks");
  }
  let tally = 0;
  let position = 0;
  for (const mark of word) {
    if (mark !== "0" && mark !== "1") {
      throw new Error("a word carries only the marks 0 and 1");
    }
    tally ^= mark === "1" ? 1 : 0;
    position = position * 2 + tally;
  }
  return position;
}
