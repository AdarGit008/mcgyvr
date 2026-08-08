type Cage = { name: string; floor: number; quota: number };

function whole(value: unknown): boolean {
  return typeof value === "number" && Number.isInteger(value);
}

export function assignLiftCalls(
  cars: Cage[],
  calls: number[],
  top: number,
): string[] {
  if (!whole(top) || top < 1) {
    throw new Error("top must be an integer of at least 1");
  }
  if (!Array.isArray(cars) || cars.length === 0) {
    throw new Error("cars must be a non-empty list");
  }
  if (!Array.isArray(calls)) {
    throw new Error("calls must be a list");
  }

  const order: string[] = [];
  const floors = new Map<string, number>();
  const quotas = new Map<string, number>();
  for (const cage of cars) {
    if (cage === null || typeof cage !== "object") {
      throw new Error("a cage must be a record");
    }
    const name = cage.name;
    if (typeof name !== "string" || name.length === 0 || name === "-") {
      throw new Error("a cage name must be a non-empty string other than -");
    }
    if (floors.has(name)) {
      throw new Error("cage names repeat: " + name);
    }
    if (!whole(cage.floor) || cage.floor < 0 || cage.floor > top) {
      throw new Error("standing floor out of the building: " + name);
    }
    if (!whole(cage.quota) || cage.quota < 1) {
      throw new Error("quota must be an integer of at least 1: " + name);
    }
    order.push(name);
    floors.set(name, cage.floor);
    quotas.set(name, cage.quota);
  }
  for (const call of calls) {
    if (!whole(call) || call < 0 || call > top) {
      throw new Error("call out of the building: " + String(call));
    }
  }

  const answered = new Map<string, number>();
  for (const name of order) {
    answered.set(name, 0);
  }

  const sheet: string[] = [];
  for (const call of calls) {
    let best = "";
    for (const name of order) {
      if ((answered.get(name) as number) >= (quotas.get(name) as number)) {
        continue;
      }
      if (best === "") {
        best = name;
        continue;
      }
      const here = Math.abs((floors.get(name) as number) - call);
      const there = Math.abs((floors.get(best) as number) - call);
      if (here !== there) {
        if (here < there) {
          best = name;
        }
        continue;
      }
      const mine = answered.get(name) as number;
      const yours = answered.get(best) as number;
      if (mine !== yours) {
        if (mine < yours) {
          best = name;
        }
        continue;
      }
      if (name < best) {
        best = name;
      }
    }
    if (best === "") {
      sheet.push("-");
      continue;
    }
    floors.set(best, call);
    answered.set(best, (answered.get(best) as number) + 1);
    sheet.push(best);
  }
  return sheet;
}
