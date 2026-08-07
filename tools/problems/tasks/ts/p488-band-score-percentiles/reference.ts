function whole(value: unknown, least: number): boolean {
  return typeof value === "number" && Number.isInteger(value) && value >= least;
}

function isRecord(value: unknown): boolean {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function bandScorePercentiles(
  sitters: any[],
  cuts: number[],
  names: string[],
): any {
  if (!Array.isArray(sitters) || sitters.length === 0) {
    throw new Error("sitters must be a list holding at least one sitter");
  }
  if (!Array.isArray(cuts) || cuts.length === 0) {
    throw new Error("cuts must be a list holding at least one cut");
  }
  for (let i = 0; i < cuts.length; i++) {
    if (!whole(cuts[i], 1) || cuts[i] > 99) {
      throw new Error("every cut must be a whole number from 1 to 99");
    }
    if (i > 0 && cuts[i] <= cuts[i - 1]) {
      throw new Error("the cuts must strictly rise");
    }
  }
  if (!Array.isArray(names) || names.length !== cuts.length + 1) {
    throw new Error("the names must be one more in number than the cuts");
  }
  const heard = new Set<string>();
  for (const name of names) {
    if (typeof name !== "string" || name.length === 0) {
      throw new Error("every name must be a non-empty string");
    }
    if (heard.has(name)) {
      throw new Error(`the name ${name} is listed twice`);
    }
    heard.add(name);
  }

  const seen = new Set<string>();
  const marks: { tag: string; score: number }[] = [];
  for (const sitter of sitters) {
    if (!isRecord(sitter)) {
      throw new Error("each sitter must be a record");
    }
    if (typeof sitter.tag !== "string" || sitter.tag.length === 0) {
      throw new Error("tag must be a non-empty string");
    }
    if (seen.has(sitter.tag)) {
      throw new Error(`two sitters answer to the tag ${sitter.tag}`);
    }
    seen.add(sitter.tag);
    if (!whole(sitter.score, 0)) {
      throw new Error("score must be a whole number of nought or more");
    }
    marks.push({ tag: sitter.tag, score: sitter.score });
  }

  const count = new Array(names.length).fill(0);
  const rows = marks.map((mark) => {
    let below = 0;
    for (const other of marks) {
      if (other.score < mark.score) {
        below += 1;
      }
    }
    const stand = Math.floor((100 * below) / marks.length);
    let place = 0;
    for (const cut of cuts) {
      if (cut <= stand) {
        place += 1;
      }
    }
    count[place] += 1;
    return { tag: mark.tag, stand, band: names[place] };
  });

  const tally = names.map((name, index) => ({ band: name, count: count[index] }));
  return { rows, tally };
}
