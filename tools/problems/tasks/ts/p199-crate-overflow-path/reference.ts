type Crate = {
  tag: string;
  weight: number;
  cap: number;
  inside: Crate[];
};

function check(raw: unknown): Crate {
  if (raw === null || typeof raw !== "object" || Array.isArray(raw)) {
    throw new Error("a crate must be a mapping");
  }
  const crate = raw as Record<string, unknown>;
  const tag = crate.tag;
  if (typeof tag !== "string" || tag.length === 0) {
    throw new Error("a crate needs a non-empty tag");
  }
  if (tag.includes(".")) {
    throw new Error("a tag may not carry a full stop: " + tag);
  }
  if (!Number.isInteger(crate.weight) || (crate.weight as number) < 0) {
    throw new Error("a weight is a non-negative whole number");
  }
  if (!Number.isInteger(crate.cap) || (crate.cap as number) <= 0) {
    throw new Error("a cap is a positive whole number");
  }
  const inside = crate.inside;
  if (!Array.isArray(inside)) {
    throw new Error("inside must be a list");
  }
  const tags = new Set<string>();
  for (const packed of inside) {
    const child = check(packed);
    if (tags.has(child.tag)) {
      throw new Error("two crates packed side by side share the tag " + child.tag);
    }
    tags.add(child.tag);
  }
  return crate as unknown as Crate;
}

function walk(crate: Crate, trail: string): { gross: number; spill: string } {
  let gross = crate.weight;
  let spill = "";
  for (const packed of crate.inside) {
    const below = walk(packed, trail + "." + packed.tag);
    gross += below.gross;
    if (spill === "" && below.spill !== "") {
      spill = below.spill;
    }
  }
  if (spill === "" && gross > crate.cap) {
    spill = trail;
  }
  return { gross, spill };
}

export function crateOverflowPath(root: Record<string, unknown>): string {
  const crate = check(root);
  return walk(crate, crate.tag).spill;
}
