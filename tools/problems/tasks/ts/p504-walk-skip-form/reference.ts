function isMapping(value: unknown): boolean {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

export function walkSkipForm(
  steps: unknown[],
  replies: Record<string, unknown>,
): Record<string, unknown> {
  if (!Array.isArray(steps) || steps.length === 0) {
    throw new Error("the steps must be a non-empty list");
  }
  const codes: string[] = [];
  const place = new Map<string, number>();
  for (const step of steps) {
    if (!isMapping(step)) throw new Error("a step must be a mapping");
    const code = (step as Record<string, unknown>).code;
    if (typeof code !== "string" || code.length === 0) {
      throw new Error("a step needs a non-empty code");
    }
    if (place.has(code)) throw new Error("two steps carry the same code");
    place.set(code, codes.length);
    codes.push(code);
  }

  const options: string[][] = [];
  const jumps: Array<Map<string, string>> = [];
  for (let index = 0; index < steps.length; index++) {
    const step = steps[index] as Record<string, unknown>;
    const choices = step.options;
    if (!Array.isArray(choices) || choices.length === 0) {
      throw new Error("a step needs a non-empty list of options");
    }
    const kept: string[] = [];
    for (const choice of choices) {
      if (typeof choice !== "string" || choice.length === 0) {
        throw new Error("an option must be a non-empty string");
      }
      if (kept.includes(choice)) throw new Error("a step repeats an option");
      kept.push(choice);
    }
    options.push(kept);
    const rules = step.jumps;
    if (!Array.isArray(rules)) throw new Error("the jumps of a step must be a list");
    const table = new Map<string, string>();
    for (const rule of rules) {
      if (!isMapping(rule)) throw new Error("a jump must be a mapping");
      const on = (rule as Record<string, unknown>).on;
      const to = (rule as Record<string, unknown>).to;
      if (typeof on !== "string" || !kept.includes(on)) {
        throw new Error("a jump must fire on one of its own step's options");
      }
      if (table.has(on)) throw new Error("two jumps of one step fire on the same option");
      if (typeof to !== "string") throw new Error("a jump needs a target");
      if (to !== "close" && !(place.has(to) && (place.get(to) as number) > index)) {
        throw new Error("a jump must go to close or to a later step");
      }
      table.set(on, to);
    }
    jumps.push(table);
  }

  if (!isMapping(replies)) throw new Error("the replies must be a mapping");
  for (const [code, value] of Object.entries(replies)) {
    if (!place.has(code)) throw new Error("a reply names no step of the form");
    if (typeof value !== "string") throw new Error("a reply must be a string");
  }

  const asked: string[] = [];
  const blank: string[] = [];
  const wrong: string[] = [];
  const reached = new Set<string>();
  let ending = "spent";
  let at = 0;
  while (at < steps.length) {
    const code = codes[at];
    asked.push(code);
    reached.add(code);
    if (!Object.prototype.hasOwnProperty.call(replies, code)) {
      blank.push(code);
      at += 1;
      continue;
    }
    const answer = replies[code] as string;
    if (!options[at].includes(answer)) {
      wrong.push(code);
      at += 1;
      continue;
    }
    const target = jumps[at].get(answer);
    if (target === undefined) {
      at += 1;
    } else if (target === "close") {
      ending = "close";
      break;
    } else {
      at = place.get(target) as number;
    }
  }

  const stray = codes.filter(
    (code) => !reached.has(code) && Object.prototype.hasOwnProperty.call(replies, code),
  );
  return { asked, blank, wrong, stray, ending };
}
