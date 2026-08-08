const UNITS = [
  "",
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
const TEENS = [
  "ten",
  "eleven",
  "twelve",
  "thirteen",
  "fourteen",
  "fifteen",
  "sixteen",
  "seventeen",
  "eighteen",
  "nineteen",
];
const ROUND = [
  "",
  "",
  "twenty",
  "thirty",
  "forty",
  "fifty",
  "sixty",
  "seventy",
  "eighty",
  "ninety",
];
const IRREGULAR: Record<string, string> = {
  one: "first",
  two: "second",
  three: "third",
  five: "fifth",
  eight: "eighth",
  nine: "ninth",
  twelve: "twelfth",
  hundred: "hundredth",
};

function counting(value: number): string {
  if (value < 10) {
    return UNITS[value];
  }
  if (value < 20) {
    return TEENS[value - 10];
  }
  if (value < 100) {
    const tens = ROUND[Math.floor(value / 10)];
    const unit = value % 10;
    return unit === 0 ? tens : `${tens}-${UNITS[unit]}`;
  }
  const hundreds = UNITS[Math.floor(value / 100)];
  const rest = value % 100;
  return rest === 0
    ? `${hundreds} hundred`
    : `${hundreds} hundred and ${counting(rest)}`;
}

function placeForm(piece: string): string {
  if (piece in IRREGULAR) {
    return IRREGULAR[piece];
  }
  if (piece.endsWith("y")) {
    return `${piece.slice(0, -1)}ieth`;
  }
  return `${piece}th`;
}

export function spellOrdinalPlace(place: number): string {
  if (typeof place !== "number" || !Number.isInteger(place)) {
    throw new Error("place must be a whole number");
  }
  if (place < 1 || place > 999) {
    throw new Error("place must lie between 1 and 999");
  }
  const words = counting(place);
  const pieces = words.split(/[- ]/);
  const tail = pieces[pieces.length - 1];
  return words.slice(0, words.length - tail.length) + placeForm(tail);
}
