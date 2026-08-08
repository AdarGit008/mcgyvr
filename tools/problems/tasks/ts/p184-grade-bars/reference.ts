export function gradeBars(
  line: string,
  beats: number,
  unit: number,
): string[] {
  if (typeof line !== "string") {
    throw new Error("line must be a string");
  }
  if (!Number.isInteger(beats) || beats < 1) {
    throw new Error("beats must be a whole number of at least one");
  }
  if (![1, 2, 4, 8, 16].includes(unit)) {
    throw new Error("unit must be 1, 2, 4, 8 or 16");
  }
  const worth: Record<string, number> = { w: 64, h: 32, q: 16, e: 8, s: 4 };
  const holds = (beats * 64) / unit;
  const verdicts: string[] = [];
  for (const bar of line.split("|")) {
    const notes = bar.split(" ").filter((piece) => piece.length > 0);
    if (notes.length === 0) {
      throw new Error("a bar holds no notes at all");
    }
    let filled = 0;
    for (const note of notes) {
      const letter = note[0];
      if (!(letter in worth)) {
        throw new Error("unknown note letter " + letter);
      }
      const tail = note.slice(1);
      if (tail !== "" && tail !== ".") {
        throw new Error("a note may carry at most one full stop");
      }
      filled += tail === "." ? worth[letter] + worth[letter] / 2 : worth[letter];
    }
    verdicts.push(filled < holds ? "short" : filled > holds ? "long" : "exact");
  }
  return verdicts;
}
