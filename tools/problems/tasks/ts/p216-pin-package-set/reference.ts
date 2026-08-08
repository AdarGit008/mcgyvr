type Trip = [number, number, number];
type Stocked = { text: string; trip: Trip };
type Want = { name: string; from: Trip; under: Trip };

function mapping(value: unknown): boolean {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function readVersion(text: unknown): Trip {
  if (typeof text !== "string") {
    throw new Error("a version must be a string");
  }
  const parts = text.split(".");
  if (parts.length !== 3) {
    throw new Error("a version must have three groups");
  }
  const trip: number[] = [];
  for (const part of parts) {
    if (!/^\d+$/.test(part)) {
      throw new Error("a version group must be digits");
    }
    if (part.length > 1 && part.startsWith("0")) {
      throw new Error("a version group must not carry a leading zero");
    }
    trip.push(Number(part));
  }
  return [trip[0], trip[1], trip[2]];
}

function under(left: Trip, right: Trip): boolean {
  for (let index = 0; index < 3; index++) {
    if (left[index] !== right[index]) {
      return left[index] < right[index];
    }
  }
  return false;
}

function readWant(raw: unknown, stock: Map<string, Stocked[]>): Want {
  if (!mapping(raw)) {
    throw new Error("a want must be a mapping");
  }
  const want = raw as Record<string, unknown>;
  const name = want.name;
  if (typeof name !== "string" || !stock.has(name)) {
    throw new Error("a want names a package the shelf does not stock");
  }
  const from = readVersion(want.from);
  const ceiling = readVersion(want.under);
  if (!under(from, ceiling)) {
    throw new Error("a want's from must be strictly below its under");
  }
  return { name, from, under: ceiling };
}

export function pinPackageSet(
  plan: Record<string, unknown>
): Record<string, unknown> {
  if (!mapping(plan)) {
    throw new Error("the plan must be a mapping");
  }
  const shelf = plan.shelf;
  const needs = plan.needs;
  const root = plan.root;
  if (!mapping(shelf)) {
    throw new Error("shelf must be a mapping");
  }
  if (!mapping(needs)) {
    throw new Error("needs must be a mapping");
  }
  if (!Array.isArray(root)) {
    throw new Error("root must be a list");
  }

  const stock = new Map<string, Stocked[]>();
  for (const [name, listed] of Object.entries(
    shelf as Record<string, unknown>
  )) {
    if (!Array.isArray(listed) || listed.length === 0) {
      throw new Error("a shelf entry must be a non-empty list");
    }
    const seenText = new Set<string>();
    const versions: Stocked[] = [];
    for (const text of listed) {
      const trip = readVersion(text);
      if (seenText.has(text as string)) {
        throw new Error("a shelf entry repeats a version");
      }
      seenText.add(text as string);
      versions.push({ text: text as string, trip });
    }
    stock.set(name, versions);
  }

  const declared = new Map<string, Want[]>();
  for (const [name, listed] of Object.entries(
    needs as Record<string, unknown>
  )) {
    if (!stock.has(name)) {
      throw new Error("needs is keyed by a package the shelf does not stock");
    }
    if (!Array.isArray(listed)) {
      throw new Error("a declared want list must be a list");
    }
    declared.set(
      name,
      listed.map((raw: unknown) => readWant(raw, stock))
    );
  }
  const queue: Want[] = root.map((raw: unknown) => readWant(raw, stock));

  const filed = new Map<string, Want[]>();
  const reached = new Set<string>();
  let head = 0;
  while (head < queue.length) {
    const want = queue[head];
    head += 1;
    const already = filed.get(want.name);
    if (already === undefined) {
      filed.set(want.name, [want]);
    } else {
      already.push(want);
    }
    if (!reached.has(want.name)) {
      reached.add(want.name);
      for (const next of declared.get(want.name) ?? []) {
        queue.push(next);
      }
    }
  }

  const picked: Record<string, string>[] = [];
  const stuck: string[] = [];
  for (const name of Array.from(reached).sort()) {
    const windows = filed.get(name) as Want[];
    const allowed = (stock.get(name) as Stocked[]).filter((version) =>
      windows.every(
        (want) =>
          !under(version.trip, want.from) && under(version.trip, want.under)
      )
    );
    if (allowed.length === 0) {
      stuck.push(name);
      continue;
    }
    let best = allowed[0];
    for (const version of allowed.slice(1)) {
      const [bm, bn, bp] = best.trip;
      const [vm, vn, vp] = version.trip;
      if (vm < bm || (vm === bm && (vn > bn || (vn === bn && vp > bp)))) {
        best = version;
      }
    }
    picked.push({ name, version: best.text });
  }
  return { picked, stuck };
}
