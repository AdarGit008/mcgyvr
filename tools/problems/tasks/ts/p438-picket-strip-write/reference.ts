function patterns(): string[] {
  const table: string[] = [];
  for (let first = 0; first < 5; first++) {
    for (let second = first + 1; second < 5; second++) {
      const bars: string[] = [];
      for (let bar = 0; bar < 5; bar++) {
        bars.push(bar === first || bar === second ? "w" : "n");
      }
      table.push(bars.join(""));
    }
  }
  return table;
}

export function writePicketStrip(digits: string): { strip: string; width: number } {
  if (typeof digits !== "string") {
    throw new Error("the digits come as a string");
  }
  if (digits.length === 0) {
    throw new Error("there are no digits to draw");
  }
  const table = patterns();
  let strip = "nn";
  for (const character of digits) {
    if (character < "0" || character > "9") {
      throw new Error("the picket code draws digits only");
    }
    strip += table[Number(character)];
  }
  strip += "wn";
  let width = 0;
  for (const bar of strip) {
    width += bar === "w" ? 2 : 1;
  }
  return { strip, width };
}
