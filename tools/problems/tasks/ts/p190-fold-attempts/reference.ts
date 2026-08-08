export function foldAttempts(records: string[]): string[] {
  if (!Array.isArray(records)) {
    throw new Error("records must be a list");
  }
  const tries = new Map<string, Map<number, string>>();
  for (const record of records) {
    if (typeof record !== "string") {
      throw new Error("every record must be a string");
    }
    const pieces = record.split(" ");
    if (pieces.length !== 3) {
      throw new Error("a record holds exactly three pieces");
    }
    const [name, tryText, outcome] = pieces;
    if (name === "") {
      throw new Error("empty case name");
    }
    if (!/^\d+$/.test(tryText)) {
      throw new Error("try number is not digits");
    }
    if (tryText.length > 1 && tryText[0] === "0") {
      throw new Error("try number carries a padding zero");
    }
    const number = Number(tryText);
    if (number === 0) {
      throw new Error("try number is zero");
    }
    if (outcome !== "pass" && outcome !== "fail") {
      throw new Error("outcome is neither pass nor fail");
    }
    let seen = tries.get(name);
    if (seen === undefined) {
      seen = new Map<number, string>();
      tries.set(name, seen);
    }
    if (seen.has(number)) {
      throw new Error("a case repeats a try number");
    }
    seen.set(number, outcome);
  }

  const settled: string[] = [];
  for (const name of [...tries.keys()].sort()) {
    const seen = tries.get(name)!;
    for (let number = 1; number <= seen.size; number += 1) {
      if (!seen.has(number)) {
        throw new Error("a case skips a try number");
      }
    }
    const outcomes = [...seen.values()];
    const passed = outcomes.filter((one) => one === "pass").length;
    const word =
      passed === outcomes.length ? "pass" : passed === 0 ? "fail" : "flake";
    settled.push(name + "=" + word);
  }
  return settled;
}
