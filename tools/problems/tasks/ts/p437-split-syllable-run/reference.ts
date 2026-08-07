const PAIRS = ["ch", "ph", "sh", "th", "wh"];

function isVowel(word: string, at: number): boolean {
  const letter = word[at];
  if ("aeiou".includes(letter)) {
    return true;
  }
  return letter === "y" && at > 0;
}

export function splitSyllables(word: string, minLetters: number): string[] {
  if (typeof word !== "string") {
    throw new Error("the word is a string");
  }
  if (word.length === 0) {
    throw new Error("the word is not empty");
  }
  if (!/^[a-z]+$/.test(word)) {
    throw new Error("the word holds only lowercase letters");
  }
  if (
    typeof minLetters !== "number" ||
    !Number.isInteger(minLetters) ||
    minLetters < 1
  ) {
    throw new Error("minLetters is a whole number of one or more");
  }

  const nuclei: Array<[number, number]> = [];
  let at = 0;
  while (at < word.length) {
    if (isVowel(word, at)) {
      const from = at;
      while (at < word.length && isVowel(word, at)) {
        at += 1;
      }
      nuclei.push([from, at - 1]);
    } else {
      at += 1;
    }
  }
  if (nuclei.length <= 1) {
    return [word];
  }

  const syllables: string[] = [];
  let start = 0;
  for (let i = 1; i < nuclei.length; i++) {
    const runStart = nuclei[i - 1][1] + 1;
    const runEnd = nuclei[i][0] - 1;
    const run = runEnd - runStart + 1;
    let cut: number;
    if (run === 1) {
      cut = runStart;
    } else if (PAIRS.includes(word.slice(runStart, runStart + 2))) {
      cut = runStart;
    } else {
      cut = runStart + 1;
    }
    syllables.push(word.slice(start, cut));
    start = cut;
  }
  syllables.push(word.slice(start));

  while (syllables.length > 1) {
    let short = -1;
    for (let i = 0; i < syllables.length; i++) {
      if (syllables[i].length < minLetters) {
        short = i;
        break;
      }
    }
    if (short === -1) {
      break;
    }
    const left = short === 0 ? 0 : short - 1;
    syllables.splice(left, 2, syllables[left] + syllables[left + 1]);
  }
  return syllables;
}
