function fragmentList(raw: unknown): string[] {
  if (!Array.isArray(raw)) {
    throw new Error("a fragment list must be a list");
  }
  const seen = new Set<string>();
  for (const fragment of raw) {
    if (typeof fragment !== "string" || fragment.length === 0) {
      throw new Error("a fragment must be a non-empty string");
    }
    if (fragment.toLowerCase() !== fragment) {
      throw new Error("a fragment must carry no capital letter");
    }
    if (seen.has(fragment)) {
      throw new Error("a fragment list repeats a fragment");
    }
    seen.add(fragment);
  }
  return raw as string[];
}

function isMapping(value: unknown): boolean {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

export function recodeAnswerSheet(
  sheet: Record<string, unknown>,
): Record<string, unknown> {
  if (!isMapping(sheet)) {
    throw new Error("the sheet must be a mapping");
  }
  const steps = sheet.steps;
  if (!Array.isArray(steps) || steps.length === 0) {
    throw new Error("the steps must be a non-empty list");
  }
  const labels: string[] = [];
  const wanted: string[][] = [];
  const barred: string[][] = [];
  const least: number[] = [];
  const seenLabel = new Set<string>();
  for (const step of steps) {
    if (!isMapping(step)) {
      throw new Error("a step must be a mapping");
    }
    const label = (step as Record<string, unknown>).label;
    if (typeof label !== "string" || label.length === 0) {
      throw new Error("a label must be a non-empty string");
    }
    if (seenLabel.has(label)) {
      throw new Error("two steps share a label");
    }
    seenLabel.add(label);
    const want = fragmentList((step as Record<string, unknown>).wanted);
    if (want.length === 0) {
      throw new Error("a step must want at least one fragment");
    }
    const bar = fragmentList((step as Record<string, unknown>).barred);
    const floor = (step as Record<string, unknown>).least;
    if (
      typeof floor !== "number" ||
      !Number.isInteger(floor) ||
      floor < 1 ||
      floor > want.length
    ) {
      throw new Error("least must be a whole number within the wanted list");
    }
    labels.push(label);
    wanted.push(want);
    barred.push(bar);
    least.push(floor);
  }
  const entries = sheet.entries;
  if (!Array.isArray(entries)) {
    throw new Error("the entries must be a list");
  }
  const coded: Array<Record<string, string>> = [];
  const loose: string[] = [];
  const used = new Set<string>();
  const seenId = new Set<string>();
  for (const entry of entries) {
    if (!isMapping(entry)) {
      throw new Error("an entry must be a mapping");
    }
    const id = (entry as Record<string, unknown>).id;
    const text = (entry as Record<string, unknown>).text;
    if (typeof id !== "string" || id.length === 0) {
      throw new Error("an id must be a non-empty string");
    }
    if (seenId.has(id)) {
      throw new Error("two entries share an id");
    }
    seenId.add(id);
    if (typeof text !== "string") {
      throw new Error("an entry's text must be a string");
    }
    const folded = text.toLowerCase().replace(/\s+/g, " ").trim();
    let chosen = "";
    for (let at = 0; at < labels.length; at++) {
      const blocked = barred[at].some((fragment) => folded.includes(fragment));
      if (blocked) continue;
      let hits = 0;
      for (const fragment of wanted[at]) {
        if (folded.includes(fragment)) hits += 1;
      }
      if (hits >= least[at]) {
        chosen = labels[at];
        break;
      }
    }
    if (chosen === "") {
      loose.push(id);
    } else {
      coded.push({ id, label: chosen });
      used.add(chosen);
    }
  }
  return {
    coded,
    loose,
    unused: labels.filter((label) => !used.has(label)),
  };
}
