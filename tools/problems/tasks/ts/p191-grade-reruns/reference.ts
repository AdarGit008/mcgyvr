export function gradeReruns(log: string[], budget: number): string[] {
  if (!Array.isArray(log)) {
    throw new Error("log must be a list");
  }
  if (!Number.isInteger(budget) || budget < 0) {
    throw new Error("budget must be a whole number of at least zero");
  }
  const goes = new Map<string, string[]>();
  for (const entry of log) {
    if (typeof entry !== "string") {
      throw new Error("every entry must be a string");
    }
    const pieces = entry.split(" ");
    if (pieces.length !== 2) {
      throw new Error("an entry holds exactly two pieces");
    }
    const [name, mark] = pieces;
    if (name === "") {
      throw new Error("empty job name");
    }
    if (mark !== "green" && mark !== "red") {
      throw new Error("mark is neither green nor red");
    }
    let marks = goes.get(name);
    if (marks === undefined) {
      marks = [];
      goes.set(name, marks);
    }
    if (marks.length > 0 && marks[marks.length - 1] === "green") {
      throw new Error("an entry for a job that has already gone green");
    }
    if (marks.length === budget + 1) {
      throw new Error("more goes than the budget allows");
    }
    marks.push(mark);
  }

  const graded: string[] = [];
  for (const name of [...goes.keys()].sort()) {
    const marks = goes.get(name)!;
    let word: string;
    if (marks[marks.length - 1] === "green") {
      word = marks.length === 1 ? "solid" : "shaky";
    } else {
      word = marks.length === budget + 1 ? "broken" : "dropped";
    }
    graded.push(name + ":" + word);
  }
  return graded;
}
