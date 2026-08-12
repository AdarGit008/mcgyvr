function wordsOf(text: string): string[] {
  const found = text.toLowerCase().match(/[a-z0-9]+/g);
  return found === null ? [] : found;
}

export function pickSnippet(query: string, sentences: string[]): string {
  if (typeof query !== "string") {
    throw new Error("query must be a string");
  }
  const wanted = new Set(wordsOf(query));
  if (wanted.size === 0) {
    throw new Error("query holds no words");
  }
  if (!Array.isArray(sentences) || sentences.length === 0) {
    throw new Error("sentences must be a non-empty list");
  }
  let bestAt = -1;
  let bestScore = 0;
  let bestSize = 0;
  for (let index = 0; index < sentences.length; index += 1) {
    const sentence = sentences[index];
    if (typeof sentence !== "string" || sentence.length === 0) {
      throw new Error("every sentence must be a non-empty string");
    }
    const found = wordsOf(sentence);
    const present = new Set(found);
    let score = 0;
    for (const word of wanted) {
      if (present.has(word)) {
        score += 1;
      }
    }
    if (score === 0) {
      continue;
    }
    if (score > bestScore) {
      bestScore = score;
      bestSize = found.length;
      bestAt = index;
    } else if (score === bestScore && found.length < bestSize) {
      bestSize = found.length;
      bestAt = index;
    }
  }
  if (bestAt === -1) {
    throw new Error("no sentence holds a query word");
  }
  return sentences[bestAt];
}
