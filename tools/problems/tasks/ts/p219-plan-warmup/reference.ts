type Item = { name: string; bytes: number; weight: number; family: string };

function whole(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value);
}

function mapping(value: unknown): boolean {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

export function planWarmup(
  brief: Record<string, unknown>
): Record<string, unknown> {
  if (!mapping(brief)) {
    throw new Error("the brief must be a mapping");
  }
  const budget = brief.budget;
  const slots = brief.slots;
  const caps = brief.caps;
  const items = brief.items;
  if (!whole(budget) || budget < 0) {
    throw new Error("budget must be a non-negative whole number");
  }
  if (!whole(slots) || slots < 1) {
    throw new Error("slots must be a positive whole number");
  }
  if (!mapping(caps)) {
    throw new Error("caps must be a mapping");
  }
  if (!Array.isArray(items)) {
    throw new Error("items must be a list");
  }
  const allowance = new Map<string, number>();
  for (const [family, cap] of Object.entries(caps as Record<string, unknown>)) {
    if (!whole(cap) || cap < 0) {
      throw new Error("a cap must be a non-negative whole number");
    }
    allowance.set(family, cap);
  }

  const names = new Set<string>();
  const lined: Item[] = [];
  for (const raw of items) {
    if (!mapping(raw)) {
      throw new Error("an item must be a mapping");
    }
    const record = raw as Record<string, unknown>;
    const name = record.name;
    if (typeof name !== "string" || name.length === 0) {
      throw new Error("a name must be a non-empty string");
    }
    if (names.has(name)) {
      throw new Error("two items share a name");
    }
    names.add(name);
    const bytes = record.bytes;
    const weight = record.weight;
    const family = record.family;
    if (!whole(bytes) || bytes < 1) {
      throw new Error("bytes must be a positive whole number");
    }
    if (!whole(weight) || weight < 0) {
      throw new Error("weight must be a non-negative whole number");
    }
    if (typeof family !== "string" || family.length === 0) {
      throw new Error("a family must be a non-empty string");
    }
    if (!allowance.has(family)) {
      throw new Error("caps does not mention a family an item belongs to");
    }
    lined.push({ name, bytes, weight, family });
  }

  lined.sort((left, right) => {
    if (left.weight !== right.weight) {
      return right.weight - left.weight;
    }
    if (left.bytes !== right.bytes) {
      return left.bytes - right.bytes;
    }
    return left.name < right.name ? -1 : left.name > right.name ? 1 : 0;
  });

  const spent = new Map<string, number>();
  const loaded: string[] = [];
  const turned: Record<string, string>[] = [];
  let places = slots;
  let spare = budget;
  for (const item of lined) {
    const used = spent.get(item.family) ?? 0;
    if (places === 0) {
      turned.push({ name: item.name, why: "slots" });
    } else if (used >= (allowance.get(item.family) as number)) {
      turned.push({ name: item.name, why: "family" });
    } else if (item.bytes > spare) {
      turned.push({ name: item.name, why: "bytes" });
    } else {
      places -= 1;
      spent.set(item.family, used + 1);
      spare -= item.bytes;
      loaded.push(item.name);
    }
  }
  return { loaded, spare, turned };
}
