/** The quantity a gauge formula names, read out of a table. */
const VALUE = /^(0|-?[1-9]\d*)$/;
const PART = /^([a-z]+)(?:\^(-?[1-9]\d*))?$/;
const LABEL = /^[a-z]+$/;

type Gauge = { value: number; units: Map<string, number> };

function readQuantity(text: unknown): Gauge {
  if (typeof text !== "string") {
    throw new Error("a quantity must be a string");
  }
  const space = text.indexOf(" ");
  const head = space === -1 ? text : text.slice(0, space);
  if (!VALUE.test(head)) {
    throw new Error("a quantity begins with a whole number");
  }
  const units = new Map<string, number>();
  if (space !== -1) {
    const tail = text.slice(space + 1);
    if (tail.length === 0) {
      throw new Error("a unit text may not be empty");
    }
    for (const part of tail.split("*")) {
      const found = PART.exec(part);
      if (found === null) {
        throw new Error("a malformed unit part");
      }
      if (units.has(found[1])) {
        throw new Error("a unit name appears twice in one unit text");
      }
      units.set(found[1], found[2] === undefined ? 1 : Number(found[2]));
    }
  }
  return { value: Number(head), units };
}

function tidy(units: Map<string, number>): Map<string, number> {
  const kept = new Map<string, number>();
  for (const [name, power] of units) {
    if (power !== 0) {
      kept.set(name, power);
    }
  }
  return kept;
}

function alike(one: Map<string, number>, two: Map<string, number>): boolean {
  if (one.size !== two.size) {
    return false;
  }
  for (const [name, power] of one) {
    if (two.get(name) !== power) {
      return false;
    }
  }
  return true;
}

function readProduct(text: string, book: Map<string, Gauge>): Gauge {
  let at = 0;
  let running: Gauge | null = null;
  let op = "*";
  for (;;) {
    let label = "";
    while (at < text.length && text[at] !== "*" && text[at] !== "/") {
      label += text[at];
      at += 1;
    }
    if (label === "") {
      throw new Error("an operand is missing");
    }
    if (!LABEL.test(label)) {
      throw new Error("a label is a run of small letters");
    }
    const one = book.get(label);
    if (one === undefined) {
      throw new Error("the table has no such label");
    }
    if (running === null) {
      running = { value: one.value, units: new Map(one.units) };
    } else if (op === "*") {
      running.value *= one.value;
      for (const [name, power] of one.units) {
        running.units.set(name, (running.units.get(name) ?? 0) + power);
      }
    } else {
      if (one.value === 0) {
        throw new Error("a divisor's number may not be zero");
      }
      if (running.value % one.value !== 0) {
        throw new Error("that division does not come out whole");
      }
      running.value = running.value / one.value;
      for (const [name, power] of one.units) {
        running.units.set(name, (running.units.get(name) ?? 0) - power);
      }
    }
    if (at >= text.length) {
      break;
    }
    op = text[at];
    at += 1;
  }
  const settled = running as Gauge;
  settled.units = tidy(settled.units);
  return settled;
}

export function readGaugeFormula(
  table: Record<string, string>,
  formula: string,
): string {
  if (table === null || typeof table !== "object" || Array.isArray(table)) {
    throw new Error("the table must be a mapping");
  }
  const book = new Map<string, Gauge>();
  for (const [label, text] of Object.entries(table)) {
    if (!LABEL.test(label)) {
      throw new Error("a table label is a run of small letters");
    }
    book.set(label, readQuantity(text));
  }
  if (typeof formula !== "string" || formula.length === 0) {
    throw new Error("the formula must be a non-empty string");
  }

  let total: Gauge | null = null;
  for (const piece of formula.split("+")) {
    const run = readProduct(piece, book);
    if (total === null) {
      total = run;
    } else {
      if (!alike(total.units, run.units)) {
        throw new Error("unlike quantities cannot be added");
      }
      total = { value: total.value + run.value, units: total.units };
    }
  }

  const answer = total as Gauge;
  const names = [...answer.units.keys()].sort();
  const head = String(answer.value === 0 ? 0 : answer.value);
  if (names.length === 0) {
    return head;
  }
  const body = names
    .map((name) => {
      const power = answer.units.get(name) as number;
      return power === 1 ? name : `${name}^${power}`;
    })
    .join("*");
  return `${head} ${body}`;
}
