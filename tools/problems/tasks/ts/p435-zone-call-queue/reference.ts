type Unit = { members: string[]; earliest: number; early: boolean };

function byName(a: string, b: string): number {
  if (a < b) return -1;
  if (a > b) return 1;
  return 0;
}

export function buildZoneQueue(
  zones: string[],
  travellers: Array<Record<string, unknown>>,
): { queue: string[]; calls: number[] } {
  if (!Array.isArray(zones) || !Array.isArray(travellers)) {
    throw new Error("buildZoneQueue expects two lists");
  }
  if (zones.length === 0) {
    throw new Error("the gate calls at least one zone");
  }
  const rank = new Map<string, number>();
  for (const label of zones) {
    if (typeof label !== "string" || label.length === 0) {
      throw new Error("a zone label is a non-empty string");
    }
    if (rank.has(label)) {
      throw new Error("the calling order writes " + label + " twice");
    }
    rank.set(label, rank.size);
  }

  const units: Unit[] = [];
  const byParty = new Map<string, number>();
  const names = new Set<string>();
  for (const row of travellers) {
    if (row === null || typeof row !== "object" || Array.isArray(row)) {
      throw new Error("a traveller is a mapping");
    }
    const name = row.name;
    const zone = row.zone;
    const party = row.party;
    const early = row.early;
    if (typeof name !== "string" || name.length === 0) {
      throw new Error("a name is a non-empty string");
    }
    if (names.has(name)) {
      throw new Error("two travellers answer to " + name);
    }
    names.add(name);
    if (typeof party !== "string") {
      throw new Error("a party is a string");
    }
    if (typeof early !== "boolean") {
      throw new Error("early is a boolean");
    }
    if (typeof zone !== "string" || !rank.has(zone)) {
      throw new Error("no call is made for that zone");
    }
    const seat = rank.get(zone);
    let id: number;
    if (party === "") {
      units.push({ members: [], earliest: seat, early: false });
      id = units.length - 1;
    } else {
      const found = byParty.get(party);
      if (found === undefined) {
        units.push({ members: [], earliest: seat, early: false });
        id = units.length - 1;
        byParty.set(party, id);
      } else {
        id = found;
      }
    }
    const unit = units[id];
    unit.members.push(name);
    unit.earliest = Math.min(unit.earliest, seat);
    unit.early = unit.early || early;
  }

  const queue: string[] = [];
  const calls: number[] = [];
  for (let i = 0; i < zones.length; i++) {
    calls.push(0);
  }
  const preboard: string[] = [];
  for (const unit of units) {
    if (unit.early) {
      for (const name of unit.members) {
        preboard.push(name);
      }
    }
  }
  preboard.sort(byName);
  for (const name of preboard) {
    queue.push(name);
  }
  for (let z = 0; z < zones.length; z++) {
    for (const unit of units) {
      if (unit.early || unit.earliest !== z) {
        continue;
      }
      const walking = [...unit.members].sort(byName);
      for (const name of walking) {
        queue.push(name);
      }
      calls[z] += walking.length;
    }
  }
  return { queue, calls };
}
