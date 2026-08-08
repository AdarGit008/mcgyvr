export function pickMergeBase(
  parents: Record<string, string[]>,
  left: string,
  right: string,
): string {
  if (
    typeof parents !== "object" ||
    parents === null ||
    Array.isArray(parents)
  ) {
    throw new Error("the history must be a mapping of revision to parents");
  }
  const names = Object.keys(parents);
  for (const name of names) {
    const listed = parents[name];
    if (!Array.isArray(listed)) {
      throw new Error(`revision ${name} does not list its parents`);
    }
    const seen = new Set<string>();
    for (const parent of listed) {
      if (typeof parent !== "string" || !Object.hasOwn(parents, parent)) {
        throw new Error(`revision ${name} names an unknown parent`);
      }
      if (seen.has(parent)) {
        throw new Error(`revision ${name} names ${parent} twice`);
      }
      seen.add(parent);
    }
  }

  const pending = new Map<string, number>();
  const children = new Map<string, string[]>();
  for (const name of names) {
    pending.set(name, parents[name].length);
    children.set(name, []);
  }
  for (const name of names) {
    for (const parent of parents[name]) {
      children.get(parent)!.push(name);
    }
  }
  const ready = names.filter((name) => pending.get(name) === 0);
  let settled = 0;
  while (ready.length > 0) {
    const name = ready.pop()!;
    settled += 1;
    for (const child of children.get(name)!) {
      const remaining = pending.get(child)! - 1;
      pending.set(child, remaining);
      if (remaining === 0) {
        ready.push(child);
      }
    }
  }
  if (settled !== names.length) {
    throw new Error("a revision descends from itself");
  }

  for (const name of [left, right]) {
    if (typeof name !== "string" || !Object.hasOwn(parents, name)) {
      throw new Error(`the history carries no revision ${name}`);
    }
  }

  const forebears = (start: string): Set<string> => {
    const reached = new Set<string>([start]);
    const stack = [start];
    while (stack.length > 0) {
      const name = stack.pop()!;
      for (const parent of parents[name]) {
        if (!reached.has(parent)) {
          reached.add(parent);
          stack.push(parent);
        }
      }
    }
    return reached;
  };

  const fromLeft = forebears(left);
  const fromRight = forebears(right);
  const shared = [...fromLeft].filter((name) => fromRight.has(name)).sort();
  if (shared.length === 0) {
    throw new Error("the two revisions share no forebear");
  }
  const covered = new Set<string>();
  for (const name of shared) {
    for (const older of forebears(name)) {
      if (older !== name) {
        covered.add(older);
      }
    }
  }
  for (const name of shared) {
    if (!covered.has(name)) {
      return name;
    }
  }
  throw new Error("the two revisions share no forebear");
}
