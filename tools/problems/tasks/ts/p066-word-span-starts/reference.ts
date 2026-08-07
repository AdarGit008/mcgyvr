export function wordSpanStarts(passage: string, query: string): number[] {
  if (typeof passage !== "string" || typeof query !== "string") {
    throw new Error("passage and query must be strings");
  }
  const tokenize = (text: string): { word: string; at: number }[] => {
    const found: { word: string; at: number }[] = [];
    for (const match of text.matchAll(/[A-Za-z0-9]+/g)) {
      found.push({ word: match[0].toLowerCase(), at: match.index });
    }
    return found;
  };
  const words = tokenize(passage);
  const wanted = tokenize(query).map((token) => token.word);
  if (wanted.length === 0) {
    throw new Error("query contains no words");
  }
  const hits: number[] = [];
  for (let i = 0; i + wanted.length <= words.length; i++) {
    let matched = true;
    for (let j = 0; j < wanted.length; j++) {
      if (words[i + j].word !== wanted[j]) {
        matched = false;
        break;
      }
    }
    if (matched) {
      hits.push(words[i].at);
    }
  }
  return hits;
}
