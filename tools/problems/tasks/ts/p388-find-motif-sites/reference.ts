const TABLE: Record<string, string> = {
  A: "A",
  C: "C",
  G: "G",
  T: "T",
  R: "AG",
  Y: "CT",
  S: "CG",
  W: "AT",
  K: "GT",
  M: "AC",
  N: "ACGT",
};

export function findMotifSites(strand: string, motif: string): number[] {
  if (typeof strand !== "string" || typeof motif !== "string") {
    throw new Error("strand and motif must both be strings");
  }
  if (motif.length === 0) {
    throw new Error("motif must not be empty");
  }
  for (const letter of strand) {
    if (!"ACGT".includes(letter)) {
      throw new Error(`strand carries ${letter}, which is not A, C, G or T`);
    }
  }
  for (const symbol of motif) {
    if (!(symbol in TABLE)) {
      throw new Error(`motif carries ${symbol}, which the table does not name`);
    }
  }

  const sites: number[] = [];
  for (let start = 0; start + motif.length <= strand.length; start++) {
    let sits = true;
    for (let offset = 0; offset < motif.length; offset++) {
      if (!TABLE[motif[offset]].includes(strand[start + offset])) {
        sits = false;
        break;
      }
    }
    if (sits) {
      sites.push(start);
    }
  }
  return sites;
}
