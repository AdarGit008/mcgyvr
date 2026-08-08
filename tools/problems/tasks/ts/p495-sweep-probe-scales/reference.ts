function whole(value: unknown): boolean {
  return typeof value === "number" && Number.isInteger(value);
}

function inRange(value: number): boolean {
  return Math.abs(value) <= 1000000;
}

function settle(num: number, den: number): number {
  if (num >= 0) {
    const up = Math.floor((2 * num + den) / (2 * den));
    return up === 0 ? 0 : up;
  }
  const down = Math.floor((2 * -num + den) / (2 * den));
  return down === 0 ? 0 : -down;
}

export function sweepProbeScales(
  channels: Record<string, unknown>[],
  samples: Record<string, unknown>[],
): Record<string, unknown> {
  if (!Array.isArray(channels)) {
    throw new Error("sweepProbeScales expects a list of channels");
  }
  const decks = new Map<string, { ladder: number[][]; bias: number }>();
  const order: string[] = [];
  for (const channel of channels) {
    if (typeof channel !== "object" || channel === null || Array.isArray(channel)) {
      throw new Error("a channel is not a record");
    }
    if (Object.keys(channel).sort().join(",") !== "bias,channel,ladder") {
      throw new Error("a channel's keys are not exactly the three named");
    }
    const name = channel["channel"];
    if (typeof name !== "string" || name.length === 0) {
      throw new Error("a channel name is not a non-empty string");
    }
    if (decks.has(name)) {
      throw new Error("two channels answer to one name");
    }
    const ladder = channel["ladder"];
    if (!Array.isArray(ladder) || ladder.length < 2) {
      throw new Error("a ladder is not a list of at least two rungs");
    }
    for (const rung of ladder) {
      if (!Array.isArray(rung) || rung.length !== 2) {
        throw new Error("a rung is not a list of exactly two entries");
      }
      for (const entry of rung) {
        if (!whole(entry)) {
          throw new Error("a rung entry is not a whole number");
        }
        if (!inRange(entry)) {
          throw new Error("a rung entry reaches beyond a million away from nought");
        }
      }
    }
    for (let i = 1; i < ladder.length; i++) {
      if (ladder[i][0] <= ladder[i - 1][0]) {
        throw new Error("the tick figures do not rise strictly from rung to rung");
      }
    }
    const bias = channel["bias"];
    if (!whole(bias)) {
      throw new Error("a bias is not a whole number");
    }
    if (!inRange(Number(bias))) {
      throw new Error("a bias reaches beyond a million away from nought");
    }
    decks.set(name, { ladder: ladder as number[][], bias: Number(bias) });
    order.push(name);
  }

  if (!Array.isArray(samples)) {
    throw new Error("sweepProbeScales expects a list of samples");
  }
  for (const sample of samples) {
    if (typeof sample !== "object" || sample === null || Array.isArray(sample)) {
      throw new Error("a sample is not a record");
    }
    if (Object.keys(sample).sort().join(",") !== "channel,count") {
      throw new Error("a sample's keys are not exactly the two named");
    }
    const name = sample["channel"];
    if (typeof name !== "string" || !decks.has(name)) {
      throw new Error("a sample names no declared channel");
    }
    if (!whole(sample["count"])) {
      throw new Error("a count is not a whole number");
    }
    if (!inRange(Number(sample["count"]))) {
      throw new Error("a count reaches beyond a million away from nought");
    }
  }

  const readings: string[] = [];
  const seen = new Map<string, number[]>();
  let low = 0;
  let high = 0;

  for (const sample of samples) {
    const name = String(sample["channel"]);
    const count = Number(sample["count"]);
    const deck = decks.get(name)!;
    const ladder = deck.ladder;
    const first = ladder[0];
    const last = ladder[ladder.length - 1];

    let num = 0;
    let den = 1;
    if (count <= first[0]) {
      num = first[1];
      if (count < first[0]) {
        low++;
      }
    } else if (count >= last[0]) {
      num = last[1];
      if (count > last[0]) {
        high++;
      }
    } else {
      let index = 0;
      while (ladder[index + 1][0] <= count) {
        index++;
      }
      const lo = ladder[index];
      const hi = ladder[index + 1];
      den = hi[0] - lo[0];
      num = lo[1] * den + (count - lo[0]) * (hi[1] - lo[1]);
    }

    const value = settle(num + deck.bias * den, den);
    readings.push(`${name} ${value}`);
    const held = seen.get(name);
    if (held === undefined) {
      seen.set(name, [value, value]);
    } else {
      held[0] = Math.min(held[0], value);
      held[1] = Math.max(held[1], value);
    }
  }

  const span: string[] = [];
  for (const name of order) {
    const held = seen.get(name);
    if (held !== undefined) {
      span.push(`${name} ${held[0]} ${held[1]}`);
    }
  }

  return { readings, low, high, span };
}
