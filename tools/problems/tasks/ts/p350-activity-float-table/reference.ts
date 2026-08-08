type Activity = { name: string; days: number; after: string[] };

export function activityFloatTable(activities: Activity[]): string[] {
  if (!Array.isArray(activities) || activities.length === 0) {
    throw new Error("the plan must be a non-empty list");
  }
  const days = new Map<string, number>();
  const waits = new Map<string, string[]>();
  for (const entry of activities) {
    if (typeof entry !== "object" || entry === null || Array.isArray(entry)) {
      throw new Error("every entry must be a mapping");
    }
    const name = entry.name;
    if (typeof name !== "string" || name.length === 0) {
      throw new Error("a name must be a non-empty string");
    }
    if (days.has(name)) {
      throw new Error("two entries share a name");
    }
    const span = entry.days;
    if (typeof span !== "number" || !Number.isInteger(span) || span <= 0) {
      throw new Error("days must be a whole number above zero");
    }
    const after = entry.after;
    if (!Array.isArray(after)) {
      throw new Error("the after list must be a list");
    }
    for (const earlier of after) {
      if (typeof earlier !== "string") {
        throw new Error("the after list must hold strings");
      }
      if (earlier === name) {
        throw new Error("an activity may not wait on itself");
      }
    }
    days.set(name, span);
    waits.set(name, [...after]);
  }
  for (const after of waits.values()) {
    for (const earlier of after) {
      if (!days.has(earlier)) {
        throw new Error("an after entry names no activity in the plan");
      }
    }
  }

  const names = [...days.keys()].sort();
  const followers = new Map<string, string[]>();
  for (const name of names) {
    followers.set(name, []);
  }
  const pending = new Map<string, number>();
  for (const name of names) {
    pending.set(name, waits.get(name).length);
    for (const earlier of waits.get(name)) {
      followers.get(earlier).push(name);
    }
  }
  const order: string[] = [];
  const ready = names.filter((name) => pending.get(name) === 0);
  while (ready.length > 0) {
    const name = ready.shift();
    order.push(name);
    for (const later of followers.get(name)) {
      pending.set(later, pending.get(later) - 1);
      if (pending.get(later) === 0) {
        ready.push(later);
      }
    }
  }
  if (order.length !== names.length) {
    throw new Error("the waiting forms a loop");
  }

  const start = new Map<string, number>();
  const finish = new Map<string, number>();
  for (const name of order) {
    let earliest = 0;
    for (const earlier of waits.get(name)) {
      earliest = Math.max(earliest, finish.get(earlier));
    }
    start.set(name, earliest);
    finish.set(name, earliest + days.get(name));
  }
  let span = 0;
  for (const name of names) {
    span = Math.max(span, finish.get(name));
  }

  const lateStart = new Map<string, number>();
  for (let i = order.length - 1; i >= 0; i -= 1) {
    const name = order[i];
    let latestFinish = span;
    for (const later of followers.get(name)) {
      latestFinish = Math.min(latestFinish, lateStart.get(later));
    }
    lateStart.set(name, latestFinish - days.get(name));
  }

  return names.map(
    (name) =>
      `${name} ${start.get(name)} ${lateStart.get(name)} ${
        lateStart.get(name) - start.get(name)
      }`,
  );
}
