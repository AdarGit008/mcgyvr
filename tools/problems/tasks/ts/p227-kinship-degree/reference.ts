function climb(
  register: Record<string, string[]>,
  start: string,
): Map<string, number> {
  const seen = new Map<string, number>([[start, 0]]);
  let frontier = [start];
  let step = 0;
  while (frontier.length > 0) {
    step += 1;
    const next: string[] = [];
    for (const name of frontier) {
      for (const up of register[name]) {
        if (up === start) throw new Error("climbing closes a loop");
        if (!seen.has(up)) {
          seen.set(up, step);
          next.push(up);
        }
      }
    }
    frontier = next;
  }
  return seen;
}

export function kinshipDegree(
  register: Record<string, string[]>,
  one: string,
  other: string,
): Record<string, unknown> {
  if (register === null || typeof register !== "object" || Array.isArray(register)) {
    throw new Error("the register must be a mapping");
  }
  const names = Object.keys(register);
  for (const name of names) {
    if (name.length === 0) throw new Error("a key must be a non-empty string");
    const forebears = register[name];
    if (!Array.isArray(forebears)) throw new Error("a forebear list must be a list");
    if (forebears.length > 2) throw new Error("nobody has three forebears");
    const held = new Set<string>();
    for (const up of forebears) {
      if (typeof up !== "string" || up.length === 0) {
        throw new Error("a forebear must be a non-empty string");
      }
      if (up === name) throw new Error("nobody is their own forebear");
      if (held.has(up)) throw new Error("a list names the same forebear twice");
      held.add(up);
      if (!Object.prototype.hasOwnProperty.call(register, up)) {
        throw new Error("a forebear is not a key of the register");
      }
    }
  }
  for (const name of names) climb(register, name);
  if (typeof one !== "string" || !Object.prototype.hasOwnProperty.call(register, one)) {
    throw new Error("the second person is not a key");
  }
  if (typeof other !== "string" || !Object.prototype.hasOwnProperty.call(register, other)) {
    throw new Error("the third person is not a key");
  }

  if (one === other) return { steps: 0, line: "direct", meet: one };
  const mine = climb(register, one);
  const theirs = climb(register, other);
  if (mine.has(other)) {
    return { steps: mine.get(other) as number, line: "direct", meet: other };
  }
  if (theirs.has(one)) {
    return { steps: theirs.get(one) as number, line: "direct", meet: one };
  }
  let meet = "";
  let steps = 0;
  for (const [name, up] of mine) {
    const down = theirs.get(name);
    if (down === undefined) continue;
    const total = up + down;
    if (meet === "" || total < steps || (total === steps && name < meet)) {
      meet = name;
      steps = total;
    }
  }
  if (meet === "") return { steps: 0, line: "apart", meet: "" };
  return { steps, line: "collateral", meet };
}
