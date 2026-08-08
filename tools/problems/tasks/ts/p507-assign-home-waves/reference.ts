export function assignHomeWaves(
  waves: unknown,
  orders: unknown,
): Record<string, unknown> {
  const isMap = (value: unknown): boolean =>
    value !== null && typeof value === "object" && !Array.isArray(value);
  if (!Array.isArray(waves) || waves.length === 0) {
    throw new Error("the waves must be a non-empty list");
  }
  const names: string[] = [];
  const homes: string[] = [];
  const caps: number[] = [];
  for (const wave of waves) {
    if (!isMap(wave)) throw new Error("a wave must be a mapping");
    const name = (wave as Record<string, unknown>).name;
    if (typeof name !== "string" || name.length === 0) {
      throw new Error("a wave needs a non-empty name");
    }
    if (names.includes(name)) throw new Error("two waves carry the same name");
    const home = (wave as Record<string, unknown>).home;
    if (typeof home !== "string" || !/^[a-z]$/.test(home)) {
      throw new Error("a home must be one lowercase letter");
    }
    if (homes.includes(home)) throw new Error("two waves keep the same home");
    const cap = (wave as Record<string, unknown>).cap;
    if (typeof cap !== "number" || !Number.isInteger(cap) || cap <= 0) {
      throw new Error("a cap must be a positive whole number");
    }
    names.push(name);
    homes.push(home);
    caps.push(cap);
  }

  if (!Array.isArray(orders)) throw new Error("the orders must be a list");
  const refs: string[] = [];
  const touched: string[][] = [];
  for (const order of orders) {
    if (!isMap(order)) throw new Error("an order must be a mapping");
    const ref = (order as Record<string, unknown>).ref;
    if (typeof ref !== "string" || ref.length === 0) {
      throw new Error("an order needs a non-empty ref");
    }
    if (refs.includes(ref)) throw new Error("two orders carry the same ref");
    const zones = (order as Record<string, unknown>).zones;
    if (!Array.isArray(zones) || zones.length === 0) {
      throw new Error("an order needs a non-empty list of zones");
    }
    const kept: string[] = [];
    for (const zone of zones) {
      if (typeof zone !== "string" || !/^[a-z]$/.test(zone)) {
        throw new Error("a zone must be one lowercase letter");
      }
      if (kept.includes(zone)) throw new Error("an order repeats a zone");
      kept.push(zone);
    }
    refs.push(ref);
    touched.push(kept);
  }

  const held: string[][] = names.map(() => []);
  const spill: string[] = [];
  for (let index = 0; index < refs.length; index++) {
    let placed = -1;
    for (let slot = 0; slot < names.length; slot++) {
      if (touched[index].includes(homes[slot]) && held[slot].length < caps[slot]) {
        placed = slot;
        break;
      }
    }
    if (placed < 0) spill.push(refs[index]);
    else held[placed].push(refs[index]);
  }

  return {
    loads: names.map((name, slot) => ({ name, refs: held[slot] })),
    spill,
  };
}
