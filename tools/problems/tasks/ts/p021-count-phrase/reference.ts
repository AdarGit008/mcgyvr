export function countPhrase(tokens: string[], phrase: string): number {
  if (typeof phrase !== "string" || phrase.trim() === "") {
    throw new Error("phrase must contain at least one word");
  }
  const words = phrase
    .split(" ")
    .filter((word) => word !== "")
    .map((word) => word.toLowerCase());
  const lowered = tokens.map((token) => token.toLowerCase());
  let count = 0;
  let i = 0;
  while (i + words.length <= lowered.length) {
    let hit = true;
    for (let k = 0; k < words.length; k++) {
      if (lowered[i + k] !== words[k]) {
        hit = false;
        break;
      }
    }
    if (hit) {
      count += 1;
      i += words.length;
    } else {
      i += 1;
    }
  }
  return count;
}
