function whole(value: unknown): boolean {
  return typeof value === "number" && Number.isInteger(value);
}

function keysAre(record: Record<string, unknown>, wanted: string): boolean {
  return Object.keys(record).sort().join(",") === wanted;
}

export function replayAgendaBoxes(
  items: Record<string, unknown>[],
  slack: number,
): Record<string, unknown> {
  if (!whole(slack) || slack < 0) {
    throw new Error("the slack is not a whole number at nought or above");
  }
  if (!Array.isArray(items)) {
    throw new Error("replayAgendaBoxes expects a list of items");
  }

  const titles = new Set<string>();
  for (const item of items) {
    if (typeof item !== "object" || item === null || Array.isArray(item)) {
      throw new Error("an item is not a record");
    }
    if (!keysAre(item, "actual,planned,rule,title")) {
      throw new Error("an item's keys are not exactly the four named");
    }
    const title = item["title"];
    if (typeof title !== "string" || title.length === 0) {
      throw new Error("a title is not a non-empty string");
    }
    if (titles.has(title)) {
      throw new Error("two items share a title");
    }
    titles.add(title);
    if (!whole(item["planned"]) || Number(item["planned"]) < 1) {
      throw new Error("planned is not a whole number above nought");
    }
    if (!whole(item["actual"]) || Number(item["actual"]) < 0) {
      throw new Error("actual is not a whole number at nought or above");
    }
    if (item["rule"] !== "absorb" && item["rule"] !== "defer") {
      throw new Error("a rule is neither absorb nor defer");
    }
  }

  const boxes = items.map((item) => Number(item["planned"]));
  const log: string[] = [];
  const carry: string[] = [];
  let clock = 0;
  let spare = slack;
  let unfunded = 0;

  for (let i = 0; i < items.length; i++) {
    const title = String(items[i]["title"]);
    const actual = Number(items[i]["actual"]);
    const box = boxes[i];
    const start = clock;

    if (items[i]["rule"] === "defer" && actual > box) {
      clock = start + box;
      log.push(`${title} ${start} ${clock} cut`);
      carry.push(`${title} ${actual - box}`);
      continue;
    }

    clock = start + actual;
    if (actual < box) {
      spare += box - actual;
      log.push(`${title} ${start} ${clock} under`);
      continue;
    }
    if (actual === box) {
      log.push(`${title} ${start} ${clock} exact`);
      continue;
    }

    let rest = actual - box;
    const drawn = Math.min(rest, spare);
    spare -= drawn;
    rest -= drawn;
    for (let j = i + 1; j < boxes.length && rest > 0; j++) {
      const given = Math.min(rest, boxes[j] - 1);
      boxes[j] -= given;
      rest -= given;
    }
    unfunded += rest;
    log.push(`${title} ${start} ${clock} over`);
  }

  return { finish: clock, spare, unfunded, log, carry };
}
