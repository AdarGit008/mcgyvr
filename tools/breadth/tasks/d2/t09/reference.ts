/** Parse a Roman numeral, then require the input to be its canonical spelling. */
export function romanToInt(input: string): number {
  if (typeof input !== "string" || input.length === 0) {
    throw new Error("input must be a non-empty string");
  }
  const values: Record<string, number> = {
    I: 1, V: 5, X: 10, L: 50, C: 100, D: 500, M: 1000,
  };
  let total = 0;
  for (let i = 0; i < input.length; i++) {
    const value = values[input[i]];
    if (value === undefined) {
      throw new Error(`invalid numeral character at index ${i}`);
    }
    const next = i + 1 < input.length ? values[input[i + 1]] : undefined;
    if (next !== undefined && value < next) {
      total -= value;
    } else {
      total += value;
    }
  }
  if (total < 1 || total > 3999) {
    throw new Error(`value ${total} is outside 1..3999`);
  }
  const ones = ["", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX"];
  const tens = ["", "X", "XX", "XXX", "XL", "L", "LX", "LXX", "LXXX", "XC"];
  const hundreds = ["", "C", "CC", "CCC", "CD", "D", "DC", "DCC", "DCCC", "CM"];
  const thousands = ["", "M", "MM", "MMM"];
  const canonical =
    thousands[Math.floor(total / 1000)] +
    hundreds[Math.floor(total / 100) % 10] +
    tens[Math.floor(total / 10) % 10] +
    ones[total % 10];
  if (canonical !== input) {
    throw new Error(`non-canonical numeral: expected ${canonical}`);
  }
  return total;
}
