const NAMES = [
  "zero",
  "one",
  "two",
  "three",
  "four",
  "five",
  "six",
  "seven",
  "eight",
  "nine",
];

export function digitWord(digit: number): string {
  return NAMES[digit];
}

export function digitWords(digits: string): string {
  const words: string[] = [];
  for (const ch of digits) {
    words.push(digitWord(Number(ch)));
  }
  return words.join(" ");
}
