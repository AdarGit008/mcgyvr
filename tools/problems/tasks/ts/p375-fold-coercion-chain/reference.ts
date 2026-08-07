const TYPES = ["bit", "whole", "ratio", "word", "empty"];

function readType(value: unknown, what: string): string {
  if (typeof value !== "string" || TYPES.indexOf(value) === -1) {
    throw new Error("the " + what + " must name one of the five value types");
  }
  return value;
}

function joined(left: string, right: string): string {
  if (left === "empty" || right === "empty") {
    throw new Error("an empty cannot be joined");
  }
  if (left === "word" || right === "word") {
    return "word";
  }
  return left === "ratio" || right === "ratio" ? "ratio" : "whole";
}

function weighed(left: string, right: string): string {
  if (left === "empty" || right === "empty") {
    throw new Error("an empty cannot be weighed");
  }
  if (left === "word" || right === "word") {
    if (left !== right) {
      throw new Error("a word cannot be weighed against a number");
    }
  }
  return "bit";
}

export function foldCoercionChain(
  start: string,
  terms: Array<Record<string, unknown>>,
): string[] {
  let running = readType(start, "starting type");
  if (!Array.isArray(terms)) {
    throw new Error("the terms must be a list");
  }
  const trail: string[] = [];
  for (const raw of terms) {
    if (typeof raw !== "object" || raw === null || Array.isArray(raw)) {
      throw new Error("every term must be a mapping");
    }
    const term = raw as Record<string, unknown>;
    const other = readType(term.type, "term type");
    if (term.op === "join") {
      running = joined(running, other);
    } else if (term.op === "weigh") {
      running = weighed(running, other);
    } else {
      throw new Error("a term's op must be join or weigh");
    }
    trail.push(running);
  }
  return trail;
}
