const SMALL =
  "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split(
    " ",
  );
const TENS = "twenty thirty forty fifty sixty seventy eighty ninety".split(" ");

function smallValue(word: string): number {
  return SMALL.indexOf(word);
}

function tensValue(word: string): number {
  const index = TENS.indexOf(word);
  return index === -1 ? -1 : 20 + 10 * index;
}

function tailValue(word: string): number {
  if (word.includes("-")) {
    const parts = word.split("-");
    if (parts.length !== 2) {
      throw new Error("a hyphen joins exactly two spellings");
    }
    const tens = tensValue(parts[0]);
    const unit = smallValue(parts[1]);
    if (tens === -1 || unit < 1 || unit > 9) {
      throw new Error("bad hyphenated pair " + word);
    }
    return tens + unit;
  }
  const tens = tensValue(word);
  if (tens !== -1) {
    return tens;
  }
  const unit = smallValue(word);
  if (unit === 0) {
    throw new Error("zero may only stand alone");
  }
  if (unit === -1) {
    throw new Error("unknown word " + word);
  }
  return unit;
}

function blockValue(words: string[]): number {
  if (words.length === 0) {
    throw new Error("a block may not be empty");
  }
  let index = 0;
  let total = 0;
  if (words.length >= 2 && words[1] === "hundred") {
    const head = smallValue(words[0]);
    if (head < 1 || head > 9) {
      throw new Error("hundred wants a one-to-nine spelling ahead of it");
    }
    total += head * 100;
    index = 2;
  } else if (words[0] === "hundred") {
    throw new Error("hundred wants a one-to-nine spelling ahead of it");
  }
  const tail = words.slice(index);
  if (tail.length > 1) {
    throw new Error("a tail is one word at most");
  }
  if (tail.length === 1) {
    if (tail[0] === "hundred") {
      throw new Error("hundred appears twice in one block");
    }
    total += tailValue(tail[0]);
  }
  return total;
}

export function readSpelledCount(phrase: string): number {
  if (typeof phrase !== "string") {
    throw new Error("readSpelledCount expects a string");
  }
  if (phrase === "" || phrase !== phrase.trim() || phrase.includes("  ")) {
    throw new Error("the phrase is not single-blank separated words");
  }
  const words = phrase.split(" ");
  if (words.length === 1 && words[0] === "zero") {
    return 0;
  }
  const scales = words.filter((word) => word === "thousand").length;
  if (scales > 1) {
    throw new Error("thousand appears twice");
  }
  if (scales === 0) {
    return blockValue(words);
  }
  const at = words.indexOf("thousand");
  const left = words.slice(0, at);
  const right = words.slice(at + 1);
  if (left.length === 0) {
    throw new Error("thousand wants a block ahead of it");
  }
  const high = blockValue(left) * 1000;
  return right.length === 0 ? high : high + blockValue(right);
}
