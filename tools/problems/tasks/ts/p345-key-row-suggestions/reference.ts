const STEPS: number[][] = [
  [0, -1],
  [0, 1],
  [-1, 0],
  [1, 0],
  [-1, -1],
  [-1, 1],
  [1, -1],
  [1, 1],
];

export function keyRowSuggestions(
  rows: string[],
  typed: string,
  lexicon: string[],
): string[] {
  if (!Array.isArray(rows) || rows.length === 0) {
    throw new Error("the drawing must be a non-empty list of rows");
  }
  const place = new Map<string, number[]>();
  for (let r = 0; r < rows.length; r += 1) {
    const row = rows[r];
    if (typeof row !== "string" || row.length === 0) {
      throw new Error("every row must be a non-empty string");
    }
    if (!/^[a-z]+$/.test(row)) {
      throw new Error("a row may hold only lowercase letters");
    }
    for (let c = 0; c < row.length; c += 1) {
      if (place.has(row[c])) {
        throw new Error("a letter is drawn twice");
      }
      place.set(row[c], [r, c]);
    }
  }
  if (typeof typed !== "string" || !/^[a-z]+$/.test(typed)) {
    throw new Error("the typed word must be a non-empty lowercase string");
  }
  for (const letter of typed) {
    if (!place.has(letter)) {
      throw new Error("a typed letter is nowhere on the drawing");
    }
  }
  if (!Array.isArray(lexicon)) {
    throw new Error("the accepted list must be a list");
  }
  for (const entry of lexicon) {
    if (typeof entry !== "string" || !/^[a-z]+$/.test(entry)) {
      throw new Error("every accepted word must be a non-empty lowercase string");
    }
  }

  const accepted = new Set(lexicon);
  if (accepted.has(typed)) {
    return [];
  }
  const found: { step: number; spot: number; word: string }[] = [];
  for (let spot = 0; spot < typed.length; spot += 1) {
    const here = place.get(typed[spot]);
    if (here === undefined) {
      continue;
    }
    for (let step = 0; step < STEPS.length; step += 1) {
      const r = here[0] + STEPS[step][0];
      const c = here[1] + STEPS[step][1];
      if (r < 0 || r >= rows.length || c < 0 || c >= rows[r].length) {
        continue;
      }
      const word = typed.slice(0, spot) + rows[r][c] + typed.slice(spot + 1);
      if (accepted.has(word)) {
        found.push({ step, spot, word });
      }
    }
  }
  found.sort((a, b) => (a.step !== b.step ? a.step - b.step : a.spot - b.spot));
  return found.map((row) => row.word);
}
