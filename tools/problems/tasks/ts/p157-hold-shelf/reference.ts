export function holdShelfReplay(slips: string[]): string[] {
  const queue: string[] = [];
  const answers: string[] = [];
  for (const slip of slips) {
    if (typeof slip !== "string") {
      throw new Error("slip must be a string");
    }
    if (slip === "serve") {
      if (queue.length === 0) {
        answers.push("idle");
      } else {
        answers.push(`take:${queue.shift()}`);
      }
    } else if (slip.startsWith("join ")) {
      const name = slip.slice(5);
      if (name === "") {
        throw new Error("missing name");
      }
      if (queue.includes(name)) {
        answers.push("no:again");
      } else {
        queue.push(name);
        answers.push(`at:${queue.length}`);
      }
    } else if (slip.startsWith("leave ")) {
      const name = slip.slice(6);
      if (name === "") {
        throw new Error("missing name");
      }
      const spot = queue.indexOf(name);
      if (spot === -1) {
        answers.push("no:absent");
      } else {
        queue.splice(spot, 1);
        answers.push("out");
      }
    } else {
      throw new Error("bad slip");
    }
  }
  return answers;
}
