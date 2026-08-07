/** Flask contents after replaying a measuring script. */
export function runPourScript(
  capacities: number[],
  script: string[],
): number[] {
  if (!Array.isArray(capacities) || capacities.length === 0) {
    throw new Error("the rack must hold at least one flask");
  }
  if (!Array.isArray(script)) {
    throw new Error("script must be a list of lines");
  }
  const held: number[] = capacities.map(() => 0);

  const markIndex = (mark: string): number => {
    if (typeof mark !== "string" || mark.length !== 1) {
      throw new Error(`unusable flask mark: ${mark}`);
    }
    const index = mark.charCodeAt(0) - 65;
    if (index < 0 || index >= capacities.length) {
      throw new Error(`no flask is marked ${mark}`);
    }
    return index;
  };

  for (const line of script) {
    if (typeof line !== "string") {
      throw new Error("every script line must be a string");
    }
    const parts = line.split(" ");
    if (parts[0] === "fill" || parts[0] === "empty") {
      if (parts.length !== 2) {
        throw new Error(`malformed line: ${line}`);
      }
      const index = markIndex(parts[1]);
      held[index] = parts[0] === "fill" ? capacities[index] : 0;
    } else if (parts[0] === "pour") {
      if (parts.length !== 3) {
        throw new Error(`malformed line: ${line}`);
      }
      const giver = markIndex(parts[1]);
      const taker = markIndex(parts[2]);
      if (giver === taker) {
        throw new Error("a flask cannot pour into itself");
      }
      const moved = Math.min(held[giver], capacities[taker] - held[taker]);
      held[giver] -= moved;
      held[taker] += moved;
    } else {
      throw new Error(`unknown action: ${parts[0]}`);
    }
  }
  return held;
}
