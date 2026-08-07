const CODE: Record<string, string> = {
  A: "A",
  C: "C",
  G: "G",
  T: "T",
  AG: "R",
  CT: "Y",
  CG: "S",
  AT: "W",
  GT: "K",
  AC: "M",
  CGT: "B",
  AGT: "D",
  ACT: "H",
  ACG: "V",
  ACGT: "N",
};

const LETTERS = ["A", "C", "G", "T"];

export function foldAlignedMotif(
  alignment: unknown,
  least: unknown,
): Record<string, unknown> {
  if (!Array.isArray(alignment) || alignment.length === 0) {
    throw new Error("alignment must be a non-empty list of rows");
  }
  for (const row of alignment) {
    if (typeof row !== "string" || row.length === 0) {
      throw new Error("every row must be a non-empty string");
    }
    if (row.length !== (alignment[0] as string).length) {
      throw new Error("every row must be the same length");
    }
    for (const letter of row) {
      if (!LETTERS.includes(letter)) {
        throw new Error(`a row holds ${letter}, which is not A, C, G or T`);
      }
    }
  }
  if (!Number.isInteger(least) || (least as number) < 1) {
    throw new Error("least must be a whole number of at least one");
  }

  const bar = least as number;
  const rows = alignment as string[];
  const width = rows[0].length;
  const codes: string[] = [];
  const outliers: number[] = [];
  for (let column = 0; column < width; column++) {
    const tally: Record<string, number> = { A: 0, C: 0, G: 0, T: 0 };
    for (const row of rows) {
      tally[row[column]] += 1;
    }
    const present = LETTERS.filter((letter) => tally[letter] > 0);
    let kept = present.filter((letter) => tally[letter] >= bar);
    if (kept.length === 0) {
      kept = present;
    } else if (kept.length < present.length) {
      outliers.push(column);
    }
    codes.push(CODE[kept.join("")]);
  }
  return { pattern: codes.join(""), outliers };
}
