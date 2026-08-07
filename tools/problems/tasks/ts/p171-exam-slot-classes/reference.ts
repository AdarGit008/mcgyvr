export function examSlotClasses(conflicts: number[][]): number[][] {
  if (!Array.isArray(conflicts) || conflicts.length === 0) {
    throw new Error("there must be at least one exam");
  }
  const total = conflicts.length;
  for (let exam = 0; exam < total; exam++) {
    const shared = conflicts[exam];
    if (!Array.isArray(shared)) {
      throw new Error("each exam needs a list of shared exams");
    }
    const seen = new Set<number>();
    for (const other of shared) {
      if (typeof other !== "number" || !Number.isInteger(other)) {
        throw new Error("a shared exam must be named by number");
      }
      if (other < 0 || other >= total) {
        throw new Error("that exam does not exist");
      }
      if (other === exam) {
        throw new Error("an exam cannot share a student with itself");
      }
      if (seen.has(other)) {
        throw new Error("the same exam is named twice");
      }
      seen.add(other);
      if (!conflicts[other].includes(exam)) {
        throw new Error("only one of the pair admits the sharing");
      }
    }
  }

  const order = Array.from({ length: total }, (_, exam) => exam);
  order.sort((one, other) => {
    const gap = conflicts[other].length - conflicts[one].length;
    return gap !== 0 ? gap : one - other;
  });

  const sitting: number[] = new Array(total).fill(-1);
  let opened = 0;
  for (const exam of order) {
    const taken = new Set<number>();
    for (const other of conflicts[exam]) {
      if (sitting[other] >= 0) {
        taken.add(sitting[other]);
      }
    }
    let pick = 0;
    while (taken.has(pick)) {
      pick += 1;
    }
    sitting[exam] = pick;
    if (pick + 1 > opened) {
      opened = pick + 1;
    }
  }

  const rows: number[][] = Array.from({ length: opened }, () => []);
  for (let exam = 0; exam < total; exam++) {
    rows[sitting[exam]].push(exam);
  }
  return rows;
}
