function whole(value: unknown): boolean {
  return typeof value === "number" && Number.isInteger(value);
}

export function layPalletRow(
  boxes: any[],
  deck: any,
): { laid: string[]; skipped: string[]; run: number; mass: number } {
  if (!Array.isArray(boxes)) {
    throw new Error("boxes must be a list");
  }
  if (deck === null || typeof deck !== "object" || Array.isArray(deck)) {
    throw new Error("deck must be a record");
  }
  for (const key of ["run", "span"]) {
    if (!whole(deck[key]) || deck[key] < 1) {
      throw new Error(`${key} must be a whole number above nought`);
    }
  }
  if (!whole(deck.load) || deck.load < 0) {
    throw new Error("load must be a whole number of nought or more");
  }

  const seen = new Set<string>();
  for (const box of boxes) {
    if (box === null || typeof box !== "object" || Array.isArray(box)) {
      throw new Error("a box must be a record");
    }
    if (typeof box.name !== "string" || box.name.length === 0) {
      throw new Error("a name must be a non-empty string");
    }
    if (seen.has(box.name)) {
      throw new Error(`two boxes answer to the name ${box.name}`);
    }
    seen.add(box.name);
    for (const key of ["alen", "blen", "mass"]) {
      if (!whole(box[key]) || box[key] < 1) {
        throw new Error(`${key} must be a whole number above nought`);
      }
    }
    if (typeof box.tender !== "boolean") {
      throw new Error("tender must be either true or false");
    }
  }

  const laid: string[] = [];
  const skipped: string[] = [];
  let run = deck.run;
  let mass = 0;
  for (const box of boxes) {
    if (mass + box.mass > deck.load) {
      skipped.push(box.name);
      continue;
    }
    const flat = box.alen <= run && box.blen <= deck.span;
    const turned = !box.tender && box.blen <= run && box.alen <= deck.span;
    if (flat) {
      laid.push(`${box.name} flat`);
      run -= box.alen;
      mass += box.mass;
    } else if (turned) {
      laid.push(`${box.name} turned`);
      run -= box.blen;
      mass += box.mass;
    } else {
      skipped.push(box.name);
    }
  }
  return { laid, skipped, run, mass };
}
