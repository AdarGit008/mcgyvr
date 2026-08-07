/** The term mark built from weighted strands with discards. */

type Piece = { score: number; available: number; at: number };

function pieces(name: string, work: unknown): Piece[] {
  if (!Array.isArray(work) || work.length === 0) {
    throw new Error("strand " + name + " carries no work");
  }
  const out: Piece[] = [];
  work.forEach((entry, at) => {
    if (!Array.isArray(entry) || entry.length !== 2) {
      throw new Error("a piece is a pair");
    }
    const [raw, available] = entry;
    if (!Number.isInteger(available) || available <= 0) {
      throw new Error("a piece must be available for a positive count");
    }
    let score: number;
    if (raw === "absent") {
      score = 0;
    } else if (Number.isInteger(raw)) {
      score = raw as number;
      if (score < 0) {
        throw new Error("a score cannot be negative");
      }
      if (score > (available as number)) {
        throw new Error("a score cannot exceed its availability");
      }
    } else {
      throw new Error("a score is a whole number or the word absent");
    }
    out.push({ score, available: available as number, at });
  });
  return out;
}

function weakestFirst(a: Piece, b: Piece): number {
  const left = a.score * b.available;
  const right = b.score * a.available;
  if (left !== right) {
    return left - right;
  }
  if (a.available !== b.available) {
    return b.available - a.available;
  }
  return a.at - b.at;
}

export function strandMarkSheet(
  strands: Array<Record<string, unknown>>
): Record<string, unknown> {
  if (!Array.isArray(strands) || strands.length === 0) {
    throw new Error("the report holds no strands");
  }
  const names = new Set<string>();
  const discarded: string[] = [];
  let shares = 0;
  let mark = 0;
  for (const strand of strands) {
    if (strand === null || typeof strand !== "object" || Array.isArray(strand)) {
      throw new Error("a strand must be a mapping");
    }
    const name = strand.name;
    if (typeof name !== "string" || name.length === 0) {
      throw new Error("a strand needs a non-empty name");
    }
    if (names.has(name)) {
      throw new Error("repeated strand name: " + name);
    }
    names.add(name);
    const share = strand.share;
    if (!Number.isInteger(share) || (share as number) < 0) {
      throw new Error("a share is a non-negative whole number");
    }
    shares += share as number;
    const discard = strand.discard;
    if (!Number.isInteger(discard) || (discard as number) < 0) {
      throw new Error("a discard count is a non-negative whole number");
    }
    const ranked = pieces(name, strand.work);
    const total = ranked.length;
    const order = ranked.slice().sort(weakestFirst);
    const count = Math.min(discard as number, total - 1);
    const gone = new Set<number>();
    for (let i = 0; i < count; i++) {
      gone.add(order[i].at);
      discarded.push(name + "#" + order[i].at);
    }
    let scored = 0;
    let available = 0;
    for (const piece of ranked) {
      if (gone.has(piece.at)) {
        continue;
      }
      scored += piece.score;
      available += piece.available;
    }
    mark += Math.floor(((share as number) * scored) / available);
  }
  if (shares !== 1000) {
    throw new Error("shares come to " + shares + ", not 1000");
  }
  return { mark, discarded };
}
