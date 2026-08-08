type Hop = {
  ref: string;
  board: string;
  alight: string;
  leaves: number;
  lands: number;
};

const PARTS = ["ref", "board", "alight", "leaves", "lands"];

function counted(value: any): boolean {
  return typeof value === "number" && Number.isInteger(value);
}

function named(value: any): boolean {
  return typeof value === "string" && value.length > 0;
}

export function checkLayovers(
  hops: any,
  layover: any,
  readyAt: any,
): { verdict: string; at: number; arrive: number } {
  if (!Array.isArray(hops) || hops.length === 0) {
    throw new Error("the hop list must be a non-empty list");
  }
  if (!counted(layover) || layover < 0) {
    throw new Error("layover must be a whole number of zero or more");
  }
  if (!counted(readyAt) || readyAt < 0) {
    throw new Error("readyAt must be a whole number of zero or more");
  }
  const chain: Hop[] = [];
  for (const raw of hops) {
    if (raw === null || typeof raw !== "object" || Array.isArray(raw)) {
      throw new Error("a hop must be a record");
    }
    for (const part of PARTS) {
      if (!Object.prototype.hasOwnProperty.call(raw, part)) {
        throw new Error("a hop is missing " + part);
      }
    }
    if (!named(raw.ref)) {
      throw new Error("a ref must be a non-empty string");
    }
    if (!named(raw.board) || !named(raw.alight)) {
      throw new Error("a halt name must be a non-empty string");
    }
    if (raw.board === raw.alight) {
      throw new Error("a hop must not board and alight at one halt");
    }
    if (!counted(raw.leaves) || !counted(raw.lands)) {
      throw new Error("leaves and lands must be whole numbers");
    }
    if (raw.lands <= raw.leaves) {
      throw new Error("lands must be past leaves");
    }
    chain.push({
      ref: raw.ref,
      board: raw.board,
      alight: raw.alight,
      leaves: raw.leaves,
      lands: raw.lands,
    });
  }
  if (chain[0].leaves < readyAt) {
    return { verdict: "early", at: 0, arrive: -1 };
  }
  for (let i = 1; i < chain.length; i++) {
    if (chain[i].board !== chain[i - 1].alight) {
      return { verdict: "place", at: i, arrive: -1 };
    }
    if (chain[i].leaves < chain[i - 1].lands + layover) {
      return { verdict: "tight", at: i, arrive: -1 };
    }
  }
  return { verdict: "sound", at: -1, arrive: chain[chain.length - 1].lands };
}
