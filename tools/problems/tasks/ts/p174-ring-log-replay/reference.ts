export function replayRingLog(
  capacity: number,
  policy: string,
  operations: string[][],
): { contents: string[]; journal: string[]; lost: number } {
  if (
    typeof capacity !== "number" ||
    !Number.isInteger(capacity) ||
    capacity < 1
  ) {
    throw new Error("the capacity must be a positive whole number");
  }
  if (policy !== "overwrite" && policy !== "refuse") {
    throw new Error("the policy must be overwrite or refuse");
  }
  if (!Array.isArray(operations)) {
    throw new Error("the operations must be a list");
  }
  const seats: string[] = [];
  const journal: string[] = [];
  let lost = 0;
  for (const operation of operations) {
    if (!Array.isArray(operation) || operation.length === 0) {
      throw new Error("an operation must be a non-empty list");
    }
    const name = operation[0];
    if (name === "push") {
      if (operation.length !== 2) {
        throw new Error("a push carries exactly one label");
      }
      const label = operation[1];
      if (typeof label !== "string" || label === "") {
        throw new Error("a label must be a non-empty string");
      }
      if (seats.length < capacity) {
        seats.push(label);
        journal.push("stored");
      } else if (policy === "overwrite") {
        const gone = seats.shift();
        seats.push(label);
        journal.push("evicted " + gone);
        lost += 1;
      } else {
        journal.push("refused");
        lost += 1;
      }
    } else if (name === "pop") {
      if (operation.length !== 1) {
        throw new Error("a pop carries nothing past its name");
      }
      if (seats.length === 0) {
        journal.push("bare");
      } else {
        journal.push("took " + seats.shift());
      }
    } else if (name === "peek") {
      if (operation.length !== 1) {
        throw new Error("a peek carries nothing past its name");
      }
      if (seats.length === 0) {
        journal.push("bare");
      } else {
        journal.push("front " + seats[0]);
      }
    } else {
      throw new Error("unknown operation name");
    }
  }
  return { contents: seats.slice(), journal, lost };
}
