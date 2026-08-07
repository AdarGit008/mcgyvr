/** The entries a squeezed line stands for. */
export function expandFoldString(line: string): string[] {
  if (typeof line !== "string" || line.length === 0) {
    throw new Error("the line must be a non-empty string");
  }
  if (!/^[a-z()|-]+$/.test(line)) {
    throw new Error("the line holds a character that has no meaning here");
  }

  let at = 0;

  function readSeries(depth: number): string[] {
    const found: string[] = [];
    for (;;) {
      for (const entry of readBranch(depth)) {
        found.push(entry);
      }
      if (at < line.length && line[at] === "|") {
        at += 1;
        continue;
      }
      return found;
    }
  }

  function readBranch(depth: number): string[] {
    if (at < line.length && line[at] === "-") {
      if (depth === 0) {
        throw new Error("a hyphen may only stand within a bracket");
      }
      at += 1;
      if (at < line.length && line[at] !== "|" && line[at] !== ")") {
        throw new Error("a hyphen must stand alone");
      }
      return [""];
    }
    const start = at;
    while (at < line.length && line[at] >= "a" && line[at] <= "z") {
      at += 1;
    }
    const stem = line.slice(start, at);
    if (stem === "") {
      throw new Error("a branch must carry a stem or a hyphen");
    }
    if (at < line.length && line[at] === "(") {
      at += 1;
      const inner = readSeries(depth + 1);
      if (at >= line.length || line[at] !== ")") {
        throw new Error("a bracket is never closed");
      }
      at += 1;
      if (at < line.length && line[at] !== "|" && line[at] !== ")") {
        throw new Error("nothing may follow a closing bracket inside a branch");
      }
      return inner.map((tail) => stem + tail);
    }
    return [stem];
  }

  const entries = readSeries(0);
  if (at !== line.length) {
    throw new Error("the line carries a bracket closed with none open");
  }
  return entries;
}
