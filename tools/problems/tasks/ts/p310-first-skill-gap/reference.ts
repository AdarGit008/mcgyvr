function readMinute(text: string): number {
  if (!/^[0-9]+$/.test(text)) {
    throw new Error("a minute is written in decimal figures");
  }
  const value = Number(text);
  if (value > 1440) {
    throw new Error("a minute never runs past 1440");
  }
  return value;
}

export function firstSkillGap(
  shifts: string[][],
  required: string[][],
): string {
  if (!Array.isArray(shifts)) {
    throw new Error("the roster must be a list");
  }
  const tours: { start: number; end: number; skills: Set<string> }[] = [];
  const rostered = new Set<string>();
  for (const row of shifts) {
    if (!Array.isArray(row) || row.length < 4) {
      throw new Error("a tour is a name, two minutes and at least one skill");
    }
    for (const field of row) {
      if (typeof field !== "string" || field.length === 0) {
        throw new Error("every tour field is a non-empty string");
      }
    }
    if (rostered.has(row[0])) {
      throw new Error("that name is rostered twice");
    }
    rostered.add(row[0]);
    const start = readMinute(row[1]);
    const end = readMinute(row[2]);
    if (start >= end) {
      throw new Error("a tour must end after it starts");
    }
    const skills = new Set<string>();
    for (const skill of row.slice(3)) {
      if (skills.has(skill)) {
        throw new Error("a tour writes one skill twice");
      }
      skills.add(skill);
    }
    tours.push({ start, end, skills });
  }

  if (!Array.isArray(required) || required.length === 0) {
    throw new Error("there must be something to demand");
  }
  const demands: { skill: string; least: number; from: number; to: number }[] =
    [];
  for (const row of required) {
    if (!Array.isArray(row) || row.length !== 4) {
      throw new Error("a demand is exactly four fields");
    }
    for (const field of row) {
      if (typeof field !== "string" || field.length === 0) {
        throw new Error("every demand field is a non-empty string");
      }
    }
    if (!/^[0-9]+$/.test(row[1])) {
      throw new Error("a headcount is written in decimal figures");
    }
    const least = Number(row[1]);
    if (least < 1) {
      throw new Error("a demand asks for at least one person");
    }
    const from = readMinute(row[2]);
    const to = readMinute(row[3]);
    if (from >= to) {
      throw new Error("a demand must close after it opens");
    }
    demands.push({ skill: row[0], least, from, to });
  }

  const cuts = new Set<number>();
  for (const tour of tours) {
    cuts.add(tour.start);
    cuts.add(tour.end);
  }
  for (const demand of demands) {
    cuts.add(demand.from);
    cuts.add(demand.to);
  }
  const marks = [...cuts].sort((a, b) => a - b);
  for (let index = 0; index + 1 < marks.length; index++) {
    const opens = marks[index];
    const closes = marks[index + 1];
    for (const demand of demands) {
      if (demand.from > opens || closes > demand.to) continue;
      let answering = 0;
      for (const tour of tours) {
        if (
          tour.start <= opens &&
          closes <= tour.end &&
          tour.skills.has(demand.skill)
        ) {
          answering += 1;
        }
      }
      if (answering < demand.least) {
        return opens + "-" + closes + " " + demand.skill;
      }
    }
  }
  return "covered";
}
