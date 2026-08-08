const WORDS = new Set(["pass", "flap", "halt"]);

export function tallyStageRetries(stages: any[], budget: number): string[] {
  if (!Number.isInteger(budget) || budget < 1) {
    throw new Error("the budget must be a whole number of one or more");
  }
  if (!Array.isArray(stages)) {
    throw new Error("the pipeline must be a list of stage records");
  }

  const lines: string[] = [];
  const seen = new Set<string>();
  let allAttempts = 0;
  let allRetries = 0;
  let allFlaps = 0;
  let allHalts = 0;
  let greens = 0;

  for (const stage of stages) {
    if (stage === null || typeof stage !== "object" || Array.isArray(stage)) {
      throw new Error("each stage must be a record");
    }
    const name = stage.name;
    if (typeof name !== "string" || name === "" || name.includes(" ")) {
      throw new Error("a stage name must be a non-empty string without spaces");
    }
    if (seen.has(name)) {
      throw new Error("repeated stage name: " + name);
    }
    seen.add(name);

    const outcomes = stage.outcomes;
    if (!Array.isArray(outcomes) || outcomes.length === 0) {
      throw new Error(name + " carries no outcomes");
    }
    if (outcomes.length > budget) {
      throw new Error(name + " carries more attempts than the budget allows");
    }
    for (let i = 0; i < outcomes.length; i++) {
      if (!WORDS.has(outcomes[i])) {
        throw new Error(name + " carries an unknown outcome");
      }
      if (i > 0 && outcomes[i - 1] !== "flap") {
        throw new Error(name + " carries an outcome after it had already ended");
      }
    }

    const attempts = outcomes.length;
    const retries = attempts - 1;
    const flaps = outcomes.filter((word: string) => word === "flap").length;
    const halts = outcomes.filter((word: string) => word === "halt").length;
    const last = outcomes[attempts - 1];
    let verdict = "open";
    if (last === "pass") {
      verdict = "green";
      greens += 1;
    } else if (last === "halt") {
      verdict = "dead";
    } else if (attempts === budget) {
      verdict = "spent";
    }

    allAttempts += attempts;
    allRetries += retries;
    allFlaps += flaps;
    allHalts += halts;
    lines.push(
      [name, attempts, retries, flaps, halts, verdict].join(" "),
    );
  }

  lines.push(["*", allAttempts, allRetries, allFlaps, allHalts, greens].join(" "));
  return lines;
}
