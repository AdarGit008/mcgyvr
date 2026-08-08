const SMALL = [
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

function underThousand(value: number): string {
  if (value < 20) {
    return SMALL[value];
  }
  if (value < 100) {
    const round = ROUND[Math.floor(value / 10)];
    const leftover = value % 10;
    return leftover === 0 ? round : round + "-" + SMALL[leftover];
  }
  const head = SMALL[Math.floor(value / 100)] + " hundred";
  const leftover = value % 100;
  return leftover === 0 ? head : head + " and " + underThousand(leftover);
}

export function spellCountWords(count: number): string {
  if (typeof count !== "number" || !Number.isInteger(count)) {
    throw new Error("spellCountWords expects a whole number");
  }
  if (count < 0 || count > 999999) {
    throw new Error("count is outside 0 through 999999");
  }
  if (count < 1000) {
    return underThousand(count);
  }
  const head = underThousand(Math.floor(count / 1000)) + " thousand";
  const leftover = count % 1000;
  if (leftover === 0) {
    return head;
  }
  return head + (leftover < 100 ? " and " : " ") + underThousand(leftover);
}
