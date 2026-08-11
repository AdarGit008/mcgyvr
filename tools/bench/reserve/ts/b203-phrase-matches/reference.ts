/** Line a token pattern up against words, a star spanning any run of them. */
export function phraseMatches(pattern: string, words: string[]): boolean {
  const tokens = pattern.split(" ").filter((token) => token.length > 0);
  return sweepTokens(tokens, words);
}

function sweepTokens(tokens: string[], words: string[]): boolean {
  if (tokens.length === 0) {
    return words.length === 0;
  }
  const head = tokens[0];
  const rest = tokens.slice(1);
  if (head === "*") {
    for (let take = 0; take <= words.length; take++) {
      if (sweepTokens(rest, words.slice(take))) {
        return true;
      }
    }
    return false;
  }
  if (words.length === 0) {
    return false;
  }
  return (head === "?" || head.split("|").includes(words[0])) && sweepTokens(rest, words.slice(1));
}
