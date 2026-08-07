/** How a run of calls fared against a protective latch. */
function whole(value: any): boolean {
  return typeof value === "number" && Number.isInteger(value) && value >= 1;
}

export function summariseLatchRun(run: any[], dial: any): any {
  if (!Array.isArray(run)) {
    throw new Error("the run must be a list");
  }
  for (const word of run) {
    if (word !== "good" && word !== "bad") {
      throw new Error("a word is either good or bad");
    }
  }
  if (dial === null || typeof dial !== "object" || Array.isArray(dial)) {
    throw new Error("the dial must be a record");
  }
  for (const key of ["span", "sour", "wait", "trials"]) {
    if (!(key in dial)) {
      throw new Error("the dial is missing " + key);
    }
    if (!whole(dial[key])) {
      throw new Error(key + " must be a whole number of one or more");
    }
  }
  if (dial.sour > dial.span) {
    throw new Error("sour may not be larger than span");
  }
  let mode = "shut";
  let countdown = 0;
  let wins = 0;
  let tried = 0;
  let shed = 0;
  let trips = 0;
  let ledger: string[] = [];
  for (const word of run) {
    if (mode === "shut") {
      tried += 1;
      ledger.push(word);
      while (ledger.length > dial.span) {
        ledger.shift();
      }
      const sourness = ledger.filter((w) => w === "bad").length;
      if (ledger.length === dial.span && sourness >= dial.sour) {
        mode = "tripped";
        countdown = dial.wait;
        trips += 1;
        ledger = [];
      }
    } else if (mode === "tripped") {
      shed += 1;
      countdown -= 1;
      if (countdown === 0) {
        mode = "testing";
        wins = 0;
      }
    } else {
      tried += 1;
      if (word === "good") {
        wins += 1;
        if (wins === dial.trials) {
          mode = "shut";
          ledger = [];
        }
      } else {
        mode = "tripped";
        countdown = dial.wait;
        trips += 1;
        ledger = [];
      }
    }
  }
  return { mode, tried, shed, trips };
}
