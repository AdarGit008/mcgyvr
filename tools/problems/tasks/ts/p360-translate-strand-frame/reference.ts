const VALUES: Record<string, number> = { W: 0, X: 1, Y: 2, Z: 3 };
const RESIDUES = "abcdefghijklmnop";
const HALTS = ["ZZW", "ZZX"];

export function translateStrandFrame(strand: string): {
  residues: string;
  halted: boolean;
} {
  if (typeof strand !== "string") {
    throw new Error("the strand must be a string");
  }
  if (strand.length === 0) {
    throw new Error("the strand must not be empty");
  }
  if (strand.length % 3 !== 0) {
    throw new Error("the strand must run in whole codons of three");
  }
  for (const symbol of strand) {
    if (!Object.hasOwn(VALUES, symbol)) {
      throw new Error("the strand holds a symbol outside W, X, Y and Z");
    }
  }
  let residues = "";
  let halted = false;
  for (let place = 0; place < strand.length; place += 3) {
    const codon = strand.slice(place, place + 3);
    if (HALTS.includes(codon)) {
      halted = true;
      break;
    }
    residues += RESIDUES[4 * VALUES[codon[0]] + VALUES[codon[1]]];
  }
  return { residues, halted };
}
