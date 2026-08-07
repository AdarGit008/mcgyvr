export function replayLoanDesk(
  stock: Record<string, number>,
  cap: number,
  events: Array<[string, string, string]>,
): string[] {
  if (typeof cap !== "number" || !Number.isInteger(cap) || cap < 1) {
    throw new Error("bad cap");
  }
  if (stock === null || typeof stock !== "object" || Array.isArray(stock)) {
    throw new Error("bad stock");
  }
  const free = new Map<string, number>();
  const loans = new Map<string, Map<string, number>>();
  const queues = new Map<string, string[]>();
  for (const [title, copies] of Object.entries(stock)) {
    if (typeof copies !== "number" || !Number.isInteger(copies) || copies < 1) {
      throw new Error("bad copy count");
    }
    free.set(title, copies);
    loans.set(title, new Map());
    queues.set(title, []);
  }
  const open = new Map<string, number>();
  const answers: string[] = [];
  for (const event of events) {
    if (!Array.isArray(event) || event.length !== 3) {
      throw new Error("bad event");
    }
    const [action, member, title] = event;
    if (!["borrow", "return", "renew", "hold"].includes(action)) {
      throw new Error("unknown action");
    }
    if (!free.has(title)) {
      answers.push("no:unknown-title");
      continue;
    }
    const titleLoans = loans.get(title) as Map<string, number>;
    const queue = queues.get(title) as string[];
    const freeNow = free.get(title) as number;
    if (action === "borrow") {
      if (titleLoans.has(member)) {
        answers.push("no:already-out");
      } else if ((open.get(member) ?? 0) >= cap) {
        answers.push("no:member-cap");
      } else if (freeNow === 0) {
        answers.push("no:none-left");
      } else if (queue.length > 0 && queue[0] !== member) {
        answers.push("no:queued-ahead");
      } else {
        if (queue[0] === member) {
          queue.shift();
        }
        titleLoans.set(member, 0);
        free.set(title, freeNow - 1);
        open.set(member, (open.get(member) ?? 0) + 1);
        answers.push("ok");
      }
    } else if (action === "return") {
      if (!titleLoans.has(member)) {
        answers.push("no:not-out");
      } else {
        titleLoans.delete(member);
        free.set(title, freeNow + 1);
        open.set(member, (open.get(member) ?? 0) - 1);
        answers.push("ok");
      }
    } else if (action === "renew") {
      if (!titleLoans.has(member)) {
        answers.push("no:not-out");
      } else if (queue.length > 0) {
        answers.push("no:on-hold");
      } else if ((titleLoans.get(member) as number) >= 2) {
        answers.push("no:renew-cap");
      } else {
        titleLoans.set(member, (titleLoans.get(member) as number) + 1);
        answers.push("ok");
      }
    } else {
      if (titleLoans.has(member)) {
        answers.push("no:own-loan");
      } else if (queue.includes(member)) {
        answers.push("no:in-queue");
      } else if (freeNow > 0) {
        answers.push("no:take-it");
      } else {
        queue.push(member);
        answers.push("ok");
      }
    }
  }
  return answers;
}
