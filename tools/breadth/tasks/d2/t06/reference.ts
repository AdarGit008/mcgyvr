/** Decode (character, count) units, validating the count grammar strictly. */
export function runLengthDecode(input: string): string {
  if (typeof input !== "string") {
    throw new Error(`input must be a string, got ${typeof input}`);
  }
  const isDigit = (ch: string): boolean => ch >= "0" && ch <= "9";
  let output = "";
  let i = 0;
  while (i < input.length) {
    const ch = input[i];
    if (isDigit(ch)) {
      throw new Error(`expected a non-digit character at index ${i}`);
    }
    i += 1;
    const countStart = i;
    while (i < input.length && isDigit(input[i])) {
      i += 1;
    }
    if (i === countStart) {
      throw new Error(`missing count for character at index ${countStart - 1}`);
    }
    if (input[countStart] === "0") {
      throw new Error(`count must not start with 0 at index ${countStart}`);
    }
    output += ch.repeat(Number(input.slice(countStart, i)));
  }
  return output;
}
