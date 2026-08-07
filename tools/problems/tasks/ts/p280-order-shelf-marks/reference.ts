export function orderShelfMarks(marks: string[]): string[] {
  if (!Array.isArray(marks) || marks.length === 0) {
    throw new Error("the batch must hold at least one mark");
  }
  const shape = /^([A-Z]{1,3}) ([1-9]\d{0,3})(?:\.(\d{1,4}))? ([a-z])(\d{1,3})$/;
  const keys = new Map<string, (string | number)[]>();
  for (const mark of marks) {
    if (typeof mark !== "string") {
      throw new Error("a mark must be a string");
    }
    if (keys.has(mark)) {
      throw new Error("the same mark was handed over twice");
    }
    const found = shape.exec(mark);
    if (found === null) {
      throw new Error("a mark departs from the Marrow shape");
    }
    const fraction = found[3] ?? "";
    if (fraction.endsWith("0")) {
      throw new Error("a fraction may not finish on a zero");
    }
    keys.set(mark, [
      found[1],
      Number(found[2]),
      (fraction + "0000").slice(0, 4),
      found[4],
      Number(found[5]),
    ]);
  }

  return [...marks].sort((left, right) => {
    const a = keys.get(left) as (string | number)[];
    const b = keys.get(right) as (string | number)[];
    for (let part = 0; part < a.length; part++) {
      if (a[part] < b[part]) {
        return -1;
      }
      if (a[part] > b[part]) {
        return 1;
      }
    }
    return 0;
  });
}
