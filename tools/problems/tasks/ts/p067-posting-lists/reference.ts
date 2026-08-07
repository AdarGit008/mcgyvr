export function postingLists(documents: string[]): Record<string, number[]> {
  if (!Array.isArray(documents)) {
    throw new Error("documents must be an array of strings");
  }
  const index: Record<string, number[]> = {};
  for (let at = 0; at < documents.length; at++) {
    const text = documents[at];
    if (typeof text !== "string") {
      throw new Error("each document must be a string");
    }
    for (const match of text.matchAll(/[A-Za-z0-9]+/g)) {
      const term = match[0].toLowerCase();
      if (term.length < 2 || /^[0-9]+$/.test(term)) {
        continue;
      }
      if (index[term] === undefined) {
        index[term] = [];
      }
      const postings = index[term];
      if (postings[postings.length - 1] !== at) {
        postings.push(at);
      }
    }
  }
  return index;
}
