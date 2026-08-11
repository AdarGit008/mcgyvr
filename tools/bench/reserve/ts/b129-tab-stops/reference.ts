/** Lay a report line's tab-separated pieces against a row of tab stops. */

function checkStops(stops: unknown): [number, string][] {
  if (!Array.isArray(stops)) {
    throw new Error("stops must be a list");
  }
  const checked: [number, string][] = [];
  let previous = 0;
  for (const stop of stops) {
    if (!Array.isArray(stop) || stop.length !== 2) {
      throw new Error("a stop is a [column, kind] pair");
    }
    const [column, kind] = stop;
    if (!Number.isInteger(column) || column < 1) {
      throw new Error("a stop column must be a positive integer");
    }
    if (kind !== "left" && kind !== "right") {
      throw new Error(`unknown stop kind: ${String(kind)}`);
    }
    if (column <= previous) {
      throw new Error("stop columns must strictly increase");
    }
    previous = column;
    checked.push([column, kind]);
  }
  return checked;
}

export function renderTabbed(line: unknown, stops: unknown): string {
  if (typeof line !== "string") {
    throw new Error("the line must be a string");
  }
  if (line.includes("\n") || line.includes("\r")) {
    throw new Error("the line must not span lines");
  }
  const row = checkStops(stops);
  const pieces = line.split("\t");
  let laid = pieces[0];
  for (const piece of pieces.slice(1)) {
    let stop: [number, string] | undefined;
    for (const candidate of row) {
      if (candidate[0] > laid.length) {
        stop = candidate;
        break;
      }
    }
    if (stop === undefined) {
      laid = `${laid} ${piece}`;
      continue;
    }
    const [column, kind] = stop;
    if (kind === "left") {
      laid = laid.padEnd(column) + piece;
      continue;
    }
    const start = column - piece.length;
    if (start <= laid.length) {
      laid = `${laid} ${piece}`;
    } else {
      laid = laid.padEnd(start) + piece;
    }
  }
  return laid;
}
