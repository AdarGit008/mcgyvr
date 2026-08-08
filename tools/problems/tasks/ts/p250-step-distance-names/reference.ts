const TABLE = [
  "unison",
  "minor second",
  "major second",
  "minor third",
  "major third",
  "perfect fourth",
  "tritone",
  "perfect fifth",
  "minor sixth",
  "major sixth",
  "minor seventh",
  "major seventh",
];
const SWEET = new Set([0, 3, 4, 5, 7, 8, 9]);

export function nameStepDistances(steps: any[]): any {
  if (!Array.isArray(steps) || steps.length === 0) {
    throw new Error("the argument must be a list holding at least one step");
  }
  const names: string[] = [];
  const lifts: number[] = [];
  const colours: string[] = [];
  const tally: Record<string, number> = {};
  let widest = 0;
  let greatest = -1;
  for (let at = 0; at < steps.length; at++) {
    const step = steps[at];
    if (!Array.isArray(step) || step.length !== 2) {
      throw new Error("a step must be a list of exactly two pitch marks");
    }
    for (const mark of step) {
      if (typeof mark !== "number" || !Number.isInteger(mark)) {
        throw new Error("a pitch mark must be a whole number");
      }
    }
    const reach = Math.abs(step[0] - step[1]);
    const lift = Math.floor(reach / 12);
    const leftover = reach % 12;
    const name = TABLE[leftover];
    names.push(name);
    lifts.push(lift);
    colours.push(SWEET.has(leftover) ? "sweet" : "sharp");
    tally[name] = (tally[name] ?? 0) + 1;
    if (reach > greatest) {
      greatest = reach;
      widest = at;
    }
  }
  return { names, lifts, colours, tally, widest };
}
