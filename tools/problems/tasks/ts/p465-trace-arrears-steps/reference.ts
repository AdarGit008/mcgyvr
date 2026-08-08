function whole(value: unknown): boolean {
  return typeof value === "number" && Number.isInteger(value);
}

export function traceArrearsSteps(
  opening: number,
  dueDay: number,
  events: Record<string, unknown>[],
): string[] {
  if (!whole(opening) || opening < 1) {
    throw new Error("the opening sum is not whole or falls below one");
  }
  if (!whole(dueDay) || dueDay < 0) {
    throw new Error("the due day is not whole or falls below nought");
  }
  if (!Array.isArray(events)) {
    throw new Error("traceArrearsSteps expects a list of events");
  }

  const labels: string[] = [];
  let owing = opening;
  let anchor = dueDay;
  let clock = 0;
  let started = false;

  for (const event of events) {
    if (typeof event !== "object" || event === null || Array.isArray(event)) {
      throw new Error("an event is not a mapping");
    }
    const kind = event["kind"];
    if (kind !== "pay" && kind !== "check") {
      throw new Error("an event's kind is outside pay and check");
    }
    const wanted = kind === "pay" ? "cents,day,kind" : "day,kind";
    if (Object.keys(event).sort().join(",") !== wanted) {
      throw new Error("an event's keys are not the ones its kind calls for");
    }
    const day = event["day"];
    if (!whole(day) || Number(day) < 0) {
      throw new Error("a day is not whole or falls below nought");
    }
    if (started && Number(day) < clock) {
      throw new Error("a day steps backwards");
    }
    clock = Number(day);
    started = true;

    if (kind === "pay") {
      const cents = event["cents"];
      if (!whole(cents) || Number(cents) < 1) {
        throw new Error("a payment is not whole or falls below one");
      }
      owing = Math.max(0, owing - Number(cents));
      if (owing > 0) {
        anchor = clock;
      }
      continue;
    }

    if (owing === 0) {
      labels.push("settled");
      continue;
    }
    const age = clock - anchor;
    if (age <= 0) {
      labels.push("current");
    } else if (age <= 9) {
      labels.push("reminder");
    } else if (age <= 24) {
      labels.push("warning");
    } else if (age <= 44) {
      labels.push("demand");
    } else {
      labels.push("referred");
    }
  }
  return labels;
}
