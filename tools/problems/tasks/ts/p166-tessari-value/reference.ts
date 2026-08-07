const GLYPHS = "KLMNPQRST";

export function tessariValue(text: string): number {
  if (typeof text !== "string") {
    throw new Error("tessariValue expects text");
  }
  if (text.length === 0) {
    throw new Error("a numeral needs at least one glyph");
  }
  let total = 0;
  for (const glyph of text) {
    const place = GLYPHS.indexOf(glyph);
    if (place < 0) {
      throw new Error(`${glyph} is not a Tessari glyph`);
    }
    total = total * 9 + place;
  }
  if (text.length > 1 && text[0] === "K") {
    throw new Error("a long numeral never opens with K");
  }
  return total;
}
