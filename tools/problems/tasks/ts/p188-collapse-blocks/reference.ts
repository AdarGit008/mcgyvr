function render(node: number, pin: number): string {
  let start = node * Math.pow(8, 4 - pin);
  const fields = [0, 0, 0, 0];
  for (let slot = 3; slot >= 0; slot -= 1) {
    fields[slot] = start % 8;
    start = Math.floor(start / 8);
  }
  return fields.join(".") + "/" + String(pin);
}

export function collapseBlocks(berths: string[]): string[] {
  if (!Array.isArray(berths)) {
    throw new Error("berths must be a list");
  }
  const leaves = new Set<number>();
  for (const berth of berths) {
    if (typeof berth !== "string") {
      throw new Error("every berth must be a string");
    }
    const fields = berth.split(".");
    if (fields.length !== 4) {
      throw new Error("a berth has exactly four fields");
    }
    let value = 0;
    for (const field of fields) {
      if (field.length !== 1 || field < "0" || field > "7") {
        throw new Error("field is not a single character between 0 and 7");
      }
      value = value * 8 + Number(field);
    }
    leaves.add(value);
  }

  const found: number[][] = [];
  const labels: string[] = [];
  let nodes = [...leaves];
  let pin = 4;
  while (pin > 0) {
    const kin = new Map<number, number[]>();
    for (const node of nodes) {
      const parent = Math.floor(node / 8);
      const siblings = kin.get(parent);
      if (siblings === undefined) {
        kin.set(parent, [node]);
      } else {
        siblings.push(node);
      }
    }
    const promoted: number[] = [];
    for (const [parent, siblings] of kin) {
      if (siblings.length === 8) {
        promoted.push(parent);
      } else {
        for (const node of siblings) {
          found.push([node * Math.pow(8, 4 - pin), labels.length]);
          labels.push(render(node, pin));
        }
      }
    }
    nodes = promoted;
    pin -= 1;
  }
  if (nodes.length > 0) {
    found.push([0, labels.length]);
    labels.push("0.0.0.0/0");
  }
  found.sort((a, b) => a[0] - b[0]);
  return found.map((entry) => labels[entry[1]]);
}
