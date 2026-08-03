/** Encode each maximal run of one character as the character and its length. */
export function runLengthEncode(input: string): string {
  if (typeof input !== "string") {
    throw new Error(`input must be a string, got ${typeof input}`);
  }
  const parts: string[] = [];
  let index = 0;
  while (index < input.length) {
    const char = input[index];
    let run = 1;
    while (index + run < input.length && input[index + run] === char) {
      run += 1;
    }
    parts.push(`${char}${run}`);
    index += run;
  }
  return parts.join("");
}
