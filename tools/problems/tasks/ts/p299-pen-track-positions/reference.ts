type Font = {
  advances: Record<string, number>;
  groups: Record<string, string>;
  pairs: [string, string, number][];
};

const BRACED = /^\{(.+)\}$/;

function plainMapping(value: unknown): boolean {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

export function penTrackPositions(
  text: string,
  font: Font,
): { positions: number[]; total: number } {
  if (typeof text !== "string") {
    throw new Error("penTrackPositions expects a string of glyphs");
  }
  if (!plainMapping(font)) {
    throw new Error("the font must be an object");
  }
  const advances = font.advances;
  const groups = font.groups;
  const pairs = font.pairs;
  if (!plainMapping(advances) || !plainMapping(groups)) {
    throw new Error("advances and groups must be plain mappings");
  }
  for (const glyph of Object.keys(advances)) {
    if (!Number.isInteger(advances[glyph]) || advances[glyph] < 0) {
      throw new Error("an advance is a whole number of zero or more: " + glyph);
    }
  }
  for (const name of Object.keys(groups)) {
    if (typeof groups[name] !== "string") {
      throw new Error("a group holds a string of glyphs: " + name);
    }
  }
  if (!Array.isArray(pairs)) {
    throw new Error("pairs must be a table list");
  }

  function checkSide(side: unknown): void {
    if (typeof side !== "string") {
      throw new Error("a side is written as text");
    }
    if (side.length === 1) {
      return;
    }
    const braced = BRACED.exec(side);
    if (braced === null || !Object.prototype.hasOwnProperty.call(groups, braced[1])) {
      throw new Error("a side is one glyph or braces around a known group: " + side);
    }
  }

  for (const row of pairs) {
    if (!Array.isArray(row) || row.length !== 3) {
      throw new Error("a row is two sides and a shift");
    }
    checkSide(row[0]);
    checkSide(row[1]);
    if (!Number.isInteger(row[2])) {
      throw new Error("a shift is a whole number");
    }
  }

  function fits(side: string, glyph: string): boolean {
    if (side.length === 1) {
      return side === glyph;
    }
    return groups[BRACED.exec(side)[1]].includes(glyph);
  }

  function shiftFor(left: string, right: string): number {
    for (const row of pairs) {
      if (fits(row[0], left) && fits(row[1], right)) {
        return row[2];
      }
    }
    return 0;
  }

  for (const glyph of text) {
    if (!Object.prototype.hasOwnProperty.call(advances, glyph)) {
      throw new Error("no advance for " + glyph);
    }
  }

  const positions: number[] = [];
  let pen = 0;
  for (let at = 0; at < text.length; at++) {
    if (at > 0) {
      pen += advances[text[at - 1]] + shiftFor(text[at - 1], text[at]);
    }
    if (pen < 0) {
      throw new Error("the pen falls below zero at glyph " + at);
    }
    positions.push(pen);
  }
  const total =
    text.length === 0 ? 0 : pen + advances[text[text.length - 1]];
  if (total < 0) {
    throw new Error("the total falls below zero");
  }
  return { positions, total };
}
