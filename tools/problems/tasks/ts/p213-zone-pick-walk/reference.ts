/** One line per row of a zoned pick walk. */
type Grab = { code: string; zone: string; row: number; slot: number; at: number };

function whole(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value);
}

function mapping(value: unknown): boolean {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

export function zonePickWalk(plan: Record<string, unknown>): string[] {
  if (!mapping(plan)) {
    throw new Error("the plan must be a mapping");
  }
  const zoneOrder = plan.zoneOrder;
  if (!Array.isArray(zoneOrder) || zoneOrder.length === 0) {
    throw new Error("zoneOrder must be a non-empty list");
  }
  const known = new Set<string>();
  for (const zone of zoneOrder) {
    if (typeof zone !== "string" || zone.length === 0) {
      throw new Error("a zone must be a non-empty string");
    }
    if (known.has(zone)) {
      throw new Error("zoneOrder repeats a zone");
    }
    known.add(zone);
  }
  const picks = plan.picks;
  if (!Array.isArray(picks)) {
    throw new Error("picks must be a list");
  }
  const codes = new Set<string>();
  const grabs: Grab[] = [];
  picks.forEach((raw: unknown, at: number) => {
    if (!mapping(raw)) {
      throw new Error("a pick must be a mapping");
    }
    const pick = raw as Record<string, unknown>;
    const code = pick.code;
    if (typeof code !== "string" || code.length === 0) {
      throw new Error("a code must be a non-empty string");
    }
    if (codes.has(code)) {
      throw new Error("two picks share a code");
    }
    codes.add(code);
    const zone = pick.zone;
    if (typeof zone !== "string" || !known.has(zone)) {
      throw new Error("a pick names a zone zoneOrder does not list");
    }
    const row = pick.row;
    const slot = pick.slot;
    if (!whole(row) || row < 1) {
      throw new Error("a row must be a positive whole number");
    }
    if (!whole(slot) || slot < 1) {
      throw new Error("a slot must be a positive whole number");
    }
    grabs.push({ code, zone, row, slot, at });
  });

  const lines: string[] = [];
  for (const zone of zoneOrder as string[]) {
    const group = grabs.filter((grab) => grab.zone === zone);
    if (group.length === 0) {
      continue;
    }
    const rows = Array.from(new Set(group.map((grab) => grab.row))).sort(
      (a, b) => a - b
    );
    rows.forEach((row: number, entered: number) => {
      const here = group.filter((grab) => grab.row === row);
      here.sort((left, right) => {
        if (left.slot !== right.slot) {
          return entered % 2 === 0
            ? left.slot - right.slot
            : right.slot - left.slot;
        }
        return left.at - right.at;
      });
      lines.push(
        zone + "/" + row + ":" + here.map((grab) => grab.code).join("|")
      );
    });
  }
  return lines;
}
