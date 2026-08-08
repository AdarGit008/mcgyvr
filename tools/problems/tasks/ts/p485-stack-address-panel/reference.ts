const FOLDS = ["keep", "up", "down"];

function isRecord(value: unknown): boolean {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function stackAddressPanel(parts: any, plan: any[]): string[] {
  if (!isRecord(parts)) {
    throw new Error("parts must be a record");
  }
  if (!Array.isArray(plan) || plan.length === 0) {
    throw new Error("plan must be a list holding at least one step");
  }
  const lines: string[] = [];
  for (const step of plan) {
    if (!isRecord(step)) {
      throw new Error("each step must be a record");
    }
    const slots = step.slots;
    if (!Array.isArray(slots) || slots.length === 0) {
      throw new Error("slots must be a list holding at least one slot name");
    }
    for (const slot of slots) {
      if (typeof slot !== "string" || slot.length === 0) {
        throw new Error("a slot name must be a non-empty string");
      }
    }
    if (typeof step.fold !== "string" || !FOLDS.includes(step.fold)) {
      throw new Error("fold must be one of keep, up, down");
    }
    if (typeof step.must !== "boolean") {
      throw new Error("must must be a boolean");
    }
    const pieces: string[] = [];
    for (const slot of slots) {
      const text = parts[slot];
      if (typeof text !== "string") {
        continue;
      }
      const trimmed = text.trim();
      if (trimmed === "") {
        continue;
      }
      pieces.push(trimmed);
    }
    if (pieces.length === 0) {
      if (step.must) {
        throw new Error(`the step wanting ${slots[0]} found nothing to write`);
      }
      continue;
    }
    const line = pieces.join(" ");
    if (step.fold === "up") {
      lines.push(line.toUpperCase());
    } else if (step.fold === "down") {
      lines.push(line.toLowerCase());
    } else {
      lines.push(line);
    }
  }
  return lines;
}
