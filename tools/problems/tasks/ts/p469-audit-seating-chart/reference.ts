export function auditSeatingChart(
  chart: string[][],
  glued: string[][],
  split: string[][],
): string[] {
  if (!Array.isArray(chart) || chart.length === 0) {
    throw new Error("the chart is not a non-empty list");
  }
  const width = Array.isArray(chart[0]) ? chart[0].length : -1;
  const spot = new Map<string, [number, number]>();
  for (let line = 0; line < chart.length; line++) {
    const band = chart[line];
    if (!Array.isArray(band) || band.length === 0) {
      throw new Error("a band of the chart is not a non-empty list");
    }
    if (band.length !== width) {
      throw new Error("the bands of the chart are not all the same length");
    }
    for (let cell = 0; cell < band.length; cell++) {
      const who = band[cell];
      if (typeof who !== "string") {
        throw new Error("a cell of the chart is not a string");
      }
      if (who === "") {
        continue;
      }
      if (spot.has(who)) {
        throw new Error("a name is written on the chart twice");
      }
      spot.set(who, [line, cell]);
    }
  }

  function readPairs(raw: unknown): string[][] {
    if (!Array.isArray(raw)) {
      throw new Error("a list of ties is not a list");
    }
    const ties: string[][] = [];
    for (const tie of raw) {
      if (!Array.isArray(tie) || tie.length !== 2) {
        throw new Error("a tie is not a list of two names");
      }
      const [one, other] = tie;
      if (typeof one !== "string" || typeof other !== "string") {
        throw new Error("a tie names something that is not a string");
      }
      if (!spot.has(one) || !spot.has(other)) {
        throw new Error("a tie names somebody the chart does not carry");
      }
      if (one === other) {
        throw new Error("a tie names one person twice");
      }
      ties.push([one, other]);
    }
    return ties;
  }

  const wanted = readPairs(glued);
  const banned = readPairs(split);

  function touching(one: string, other: string): boolean {
    const here = spot.get(one);
    const there = spot.get(other);
    if (here === undefined || there === undefined) {
      return false;
    }
    const gapDown = Math.abs(here[0] - there[0]);
    const gapAcross = Math.abs(here[1] - there[1]);
    return (
      (gapDown === 0 && gapAcross === 1) || (gapAcross === 0 && gapDown === 1)
    );
  }

  const label = (one: string, other: string) =>
    one < other ? one + "-" + other : other + "-" + one;

  const faults: string[] = [];
  for (const [one, other] of wanted) {
    if (!touching(one, other)) {
      faults.push("split:" + label(one, other));
    }
  }
  for (const [one, other] of banned) {
    if (touching(one, other)) {
      faults.push("touching:" + label(one, other));
    }
  }
  return faults;
}
