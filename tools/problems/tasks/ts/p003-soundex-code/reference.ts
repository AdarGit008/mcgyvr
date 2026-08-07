const GROUPS: [string, string][] = [
  ["bfpv", "1"],
  ["cgjkqsxz", "2"],
  ["dt", "3"],
  ["l", "4"],
  ["mn", "5"],
  ["r", "6"],
];

function digitFor(letter: string): string {
  for (const [letters, digit] of GROUPS) {
    if (letters.includes(letter)) {
      return digit;
    }
  }
  return "";
}

export function soundexCode(word: string): string {
  if (typeof word !== "string") {
    throw new Error("soundexCode expects a string");
  }
  if (!/^[A-Za-z]+$/.test(word)) {
    throw new Error("word must be one or more ASCII letters");
  }
  const lower = word.toLowerCase();
  let result = lower[0].toUpperCase();
  let previous = digitFor(lower[0]);
  for (const letter of lower.slice(1)) {
    if (letter === "h" || letter === "w") {
      continue;
    }
    const digit = digitFor(letter);
    if (digit === "") {
      previous = "";
      continue;
    }
    if (digit !== previous) {
      result += digit;
    }
    previous = digit;
  }
  return (result + "000").slice(0, 4);
}
