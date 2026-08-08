export function spreadNightDuty(
  crew: string[],
  weights: number[],
  away: string[][],
): string[] {
  if (!Array.isArray(crew) || crew.length === 0) {
    throw new Error("the crew must hold at least one person");
  }
  const known = new Set<string>();
  for (const name of crew) {
    if (typeof name !== "string" || name.length === 0) {
      throw new Error("a crew name must be a non-empty string");
    }
    if (name === "?") {
      throw new Error("the mark ? is not a crew name");
    }
    if (known.has(name)) {
      throw new Error("the crew repeats a name");
    }
    known.add(name);
  }
  if (!Array.isArray(weights) || weights.length === 0) {
    throw new Error("there must be at least one night");
  }
  for (const weight of weights) {
    if (weight !== 1 && weight !== 2) {
      throw new Error("a night weighs 1 or 2");
    }
  }
  if (!Array.isArray(away) || away.length !== weights.length) {
    throw new Error("away must run the same length as weights");
  }
  for (const entry of away) {
    if (!Array.isArray(entry)) {
      throw new Error("an away entry must be a list");
    }
    for (const name of entry) {
      if (!known.has(name)) {
        throw new Error("an away entry names somebody outside the crew");
      }
    }
  }

  const load = new Map<string, number>(crew.map((name) => [name, 0]));
  const worked = new Map<string, number>();
  const nights: string[] = [];

  for (let night = 0; night < weights.length; night++) {
    let chosen = "";
    for (const name of [...crew].sort()) {
      if (away[night].includes(name)) {
        continue;
      }
      const last = worked.get(name);
      if (last !== undefined && night - last <= 2) {
        continue;
      }
      if (chosen === "" || (load.get(name) as number) < (load.get(chosen) as number)) {
        chosen = name;
      }
    }
    if (chosen === "") {
      nights.push("?");
      continue;
    }
    load.set(chosen, (load.get(chosen) as number) + weights[night]);
    worked.set(chosen, night);
    nights.push(chosen);
  }
  return nights;
}
