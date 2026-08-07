const VALUES: Record<string, number> = { W: 0, X: 1, Y: 2, Z: 3 };
const RESIDUES = "abcdefghijklmnop";
const OPENER = "ZWX";
const HALTS = ["ZZW", "ZZX"];

function residueOf(codon: string): string {
  return RESIDUES[4 * VALUES[codon[0]] + VALUES[codon[1]]];
}

export function pickLongestSegment(strand: string): {
  frame: number;
  start: number;
  residues: string;
} {
  if (typeof strand !== "string") {
    throw new Error("the strand must be a string");
  }
  if (strand.length === 0) {
    throw new Error("the strand must not be empty");
  }
  for (const symbol of strand) {
    if (!Object.hasOwn(VALUES, symbol)) {
      throw new Error("the strand holds a symbol outside W, X, Y and Z");
    }
  }
  let bestFrame = -1;
  let bestStart = -1;
  let bestResidues = "";
  let found = false;
  for (const frame of [0, 1, 2]) {
    const places: number[] = [];
    const codons: string[] = [];
    for (let place = frame; place + 3 <= strand.length; place += 3) {
      places.push(place);
      codons.push(strand.slice(place, place + 3));
    }
    for (let opening = 0; opening < codons.length; opening++) {
      if (codons[opening] !== OPENER) {
        continue;
      }
      let residues = residueOf(OPENER);
      let complete = false;
      for (let onward = opening + 1; onward < codons.length; onward++) {
        if (HALTS.includes(codons[onward])) {
          complete = true;
          break;
        }
        residues += residueOf(codons[onward]);
      }
      if (!complete) {
        continue;
      }
      const start = places[opening];
      let better = !found;
      if (found) {
        if (residues.length !== bestResidues.length) {
          better = residues.length > bestResidues.length;
        } else if (frame !== bestFrame) {
          better = frame < bestFrame;
        } else {
          better = start < bestStart;
        }
      }
      if (better) {
        found = true;
        bestFrame = frame;
        bestStart = start;
        bestResidues = residues;
      }
    }
  }
  if (!found) {
    return { frame: -1, start: -1, residues: "" };
  }
  return { frame: bestFrame, start: bestStart, residues: bestResidues };
}
