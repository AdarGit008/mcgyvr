/** Close out a stockroom count sheet after a day's receive and issue moves. */

function parseSheet(opening: string): Map<string, number> {
  const held = new Map<string, number>();
  if (opening === "") {
    return held;
  }
  for (const part of opening.split(";")) {
    const colon = part.indexOf(":");
    if (colon < 0) {
      throw new Error(`sheet entry has no colon: ${part}`);
    }
    const name = part.slice(0, colon);
    const count = part.slice(colon + 1);
    if (!/^[a-z]+$/.test(name)) {
      throw new Error(`bad item name: ${part}`);
    }
    if (!/^(?:0|[1-9]\d*)$/.test(count)) {
      throw new Error(`bad count: ${part}`);
    }
    if (held.has(name)) {
      throw new Error(`duplicate sheet entry: ${name}`);
    }
    held.set(name, Number(count));
  }
  return held;
}

function applyMoves(held: Map<string, number>, moves: string): void {
  if (moves === "") {
    return;
  }
  for (const part of moves.split(";")) {
    const match = /^([a-z]+)([+-])([1-9]\d*)$/.exec(part);
    if (match === null) {
      throw new Error(`malformed move: ${part}`);
    }
    const name = match[1];
    const qty = Number(match[3]);
    if (match[2] === "+") {
      held.set(name, (held.get(name) ?? 0) + qty);
      continue;
    }
    const onHand = held.get(name);
    if (onHand === undefined) {
      throw new Error(`issue of an item not on the sheet: ${name}`);
    }
    if (qty > onHand) {
      throw new Error(`issue of ${qty} exceeds the ${onHand} on hand`);
    }
    held.set(name, onHand - qty);
  }
}

export function closingSheet(opening: string, moves: string): string {
  if (typeof opening !== "string" || typeof moves !== "string") {
    throw new Error("closingSheet expects two strings");
  }
  const held = parseSheet(opening);
  applyMoves(held, moves);
  const entries: string[] = [];
  for (const name of [...held.keys()].sort()) {
    const count = held.get(name);
    if (count !== 0) {
      entries.push(`${name}:${count}`);
    }
  }
  return entries.join(";");
}
