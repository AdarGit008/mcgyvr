function reads(left: string[], right: string[]): number {
  for (let i = 0; i < Math.min(left.length, right.length); i++) {
    if (left[i] !== right[i]) {
      return left[i] < right[i] ? -1 : 1;
    }
  }
  return left.length - right.length;
}

export function buildSetMeal(courses: any[], quarrels: any[]): any {
  if (!Array.isArray(courses) || courses.length === 0) {
    throw new Error("a set meal needs at least one course");
  }
  if (courses.length > 6) {
    throw new Error("more than six courses is too many");
  }
  if (!Array.isArray(quarrels)) {
    throw new Error("the quarrels must be a list of pairs");
  }

  const offered = new Set<string>();
  for (const course of courses) {
    if (!Array.isArray(course) || course.length === 0) {
      throw new Error("a course must offer at least one option");
    }
    if (course.length > 6) {
      throw new Error("a course may not offer more than six options");
    }
    for (const option of course) {
      if (option === null || typeof option !== "object" || Array.isArray(option)) {
        throw new Error("each option must be a record");
      }
      if (typeof option.code !== "string" || option.code === "") {
        throw new Error("a code must be a non-empty string");
      }
      if (offered.has(option.code)) {
        throw new Error("the code " + option.code + " is offered twice");
      }
      offered.add(option.code);
      if (!Number.isInteger(option.price) || option.price < 1) {
        throw new Error("a price must be a whole number of pence, one or more");
      }
    }
  }

  const pairs: string[][] = [];
  for (const quarrel of quarrels) {
    if (!Array.isArray(quarrel) || quarrel.length !== 2) {
      throw new Error("a quarrel must be a pair of codes");
    }
    const [left, right] = quarrel;
    if (!offered.has(left) || !offered.has(right)) {
      throw new Error("a quarrel names a code no course offers");
    }
    if (left === right) {
      throw new Error("a quarrel writes the code " + left + " twice");
    }
    pairs.push([left, right]);
  }

  const counts = courses.map((course) => course.length);
  const at = new Array(courses.length).fill(0);
  let bestTotal = 0;
  let bestPicks: string[] | null = null;
  for (;;) {
    const picks: string[] = [];
    let total = 0;
    for (let i = 0; i < courses.length; i++) {
      picks.push(courses[i][at[i]].code);
      total += courses[i][at[i]].price;
    }
    const chosen = new Set(picks);
    const calm = pairs.every(
      (pair) => !(chosen.has(pair[0]) && chosen.has(pair[1])),
    );
    if (
      calm &&
      (bestPicks === null ||
        total < bestTotal ||
        (total === bestTotal && reads(picks, bestPicks) < 0))
    ) {
      bestTotal = total;
      bestPicks = picks;
    }
    let dial = courses.length - 1;
    while (dial >= 0) {
      at[dial] += 1;
      if (at[dial] < counts[dial]) {
        break;
      }
      at[dial] = 0;
      dial -= 1;
    }
    if (dial < 0) {
      break;
    }
  }

  if (bestPicks === null) {
    throw new Error("no tray avoids every quarrel");
  }
  return { total: bestTotal, picks: bestPicks };
}
