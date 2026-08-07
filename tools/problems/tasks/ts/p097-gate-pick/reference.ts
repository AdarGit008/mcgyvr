const CLAUSE = /^(0|[1-9]\d*)?:(0|[1-9]\d*)?((?:\^(?:0|[1-9]\d*))*)$/;

export function pickBuild(gate: string, offers: number[]): number {
  if (typeof gate !== "string") {
    throw new Error("gate must be a string");
  }
  const clauses: { lo: number | null; hi: number | null; out: Set<number> }[] = [];
  for (const part of gate.split(",")) {
    const m = CLAUSE.exec(part);
    if (m === null) {
      throw new Error(`malformed clause: ${part}`);
    }
    const lo = m[1] === undefined ? null : Number(m[1]);
    const hi = m[2] === undefined ? null : Number(m[2]);
    if (lo !== null && hi !== null && lo > hi) {
      throw new Error(`ends out of order: ${part}`);
    }
    const out = new Set<number>();
    for (const carved of m[3] === "" ? [] : m[3].slice(1).split("^").map(Number)) {
      if ((lo !== null && carved < lo) || (hi !== null && carved > hi)) {
        throw new Error(`carve-out not covered by its clause: ${part}`);
      }
      out.add(carved);
    }
    clauses.push({ lo, hi, out });
  }
  for (const offer of offers) {
    if (!Number.isInteger(offer) || offer < 0) {
      throw new Error("offers must be non-negative integers");
    }
  }
  let best = -1;
  for (const offer of offers) {
    const admitted = clauses.some(
      ({ lo, hi, out }) =>
        (lo === null || offer >= lo) && (hi === null || offer <= hi) && !out.has(offer),
    );
    if (admitted && offer > best) {
      best = offer;
    }
  }
  return best;
}
