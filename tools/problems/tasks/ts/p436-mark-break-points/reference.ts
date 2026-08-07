const LETTERS = /^[a-z]+$/;

export function hyphenateWord(
  word: string,
  rules: string[],
  minPiece: number,
): string[] {
  if (typeof word !== "string") {
    throw new Error("the word is a string");
  }
  if (word.length === 0) {
    throw new Error("the word is not empty");
  }
  if (!LETTERS.test(word)) {
    throw new Error("the word holds only lowercase letters");
  }
  if (!Array.isArray(rules)) {
    throw new Error("the rules are a list of patterns");
  }
  if (
    typeof minPiece !== "number" ||
    !Number.isInteger(minPiece) ||
    minPiece < 1
  ) {
    throw new Error("minPiece is a whole number of one or more");
  }

  const pairs: Array<[string, string]> = [];
  for (const pattern of rules) {
    if (typeof pattern !== "string") {
      throw new Error("a pattern is a string");
    }
    const sides = pattern.split("-");
    if (sides.length !== 2) {
      throw new Error("a pattern carries exactly one hyphen");
    }
    if (!LETTERS.test(sides[0]) || !LETTERS.test(sides[1])) {
      throw new Error("both sides of a pattern are runs of lowercase letters");
    }
    pairs.push([sides[0], sides[1]]);
  }

  const permitted: boolean[] = [];
  for (let i = 0; i < word.length; i++) {
    permitted.push(false);
  }
  for (const [left, right] of pairs) {
    for (let i = 1; i < word.length; i++) {
      if (word.slice(0, i).endsWith(left) && word.slice(i).startsWith(right)) {
        permitted[i] = true;
      }
    }
  }

  const pieces: string[] = [];
  let start = 0;
  for (let i = 1; i < word.length; i++) {
    if (!permitted[i]) {
      continue;
    }
    if (i - start >= minPiece && word.length - i >= minPiece) {
      pieces.push(word.slice(start, i));
      start = i;
    }
  }
  pieces.push(word.slice(start));
  return pieces;
}
