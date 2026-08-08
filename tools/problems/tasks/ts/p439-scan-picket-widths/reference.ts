function groupTable(): string[] {
  const table: string[] = [];
  for (let first = 0; first < 5; first++) {
    for (let second = first + 1; second < 5; second++) {
      const places: string[] = [];
      for (let place = 0; place < 5; place++) {
        places.push(place === first || place === second ? "f" : "t");
      }
      table.push(places.join(""));
    }
  }
  return table;
}

export function readScannedBars(sweep: number[]): { digits: string; thin: number } {
  if (!Array.isArray(sweep)) {
    throw new Error("the sweep is a list of measures");
  }
  if (sweep.length < 9) {
    throw new Error("a strip never sweeps fewer than nine bars");
  }
  for (const measure of sweep) {
    if (typeof measure !== "number" || !Number.isInteger(measure) || measure < 1) {
      throw new Error("a measure is a whole number of one or more");
    }
  }
  let thin = sweep[0];
  for (const measure of sweep) {
    if (measure < thin) {
      thin = measure;
    }
  }

  const read: string[] = [];
  for (const measure of sweep) {
    if (2 * measure < 3 * thin) {
      read.push("t");
    } else if (2 * measure > 3 * thin && measure <= 3 * thin) {
      read.push("f");
    } else {
      throw new Error("a bar measuring " + String(measure) + " spoils the sweep");
    }
  }
  if (read[0] !== "t" || read[1] !== "t") {
    throw new Error("the opening mark is two thin bars");
  }
  if (read[read.length - 2] !== "f" || read[read.length - 1] !== "t") {
    throw new Error("the closing mark is a fat bar and a thin bar");
  }
  const body = read.slice(2, read.length - 2);
  if (body.length === 0 || body.length % 5 !== 0) {
    throw new Error("the bars between the marks do not divide into groups of five");
  }

  const table = groupTable();
  let digits = "";
  for (let at = 0; at < body.length; at += 5) {
    const group = body.slice(at, at + 5).join("");
    const digit = table.indexOf(group);
    if (digit < 0) {
      throw new Error("a group carries other than two fat bars");
    }
    digits += String(digit);
  }
  return { digits, thin };
}
