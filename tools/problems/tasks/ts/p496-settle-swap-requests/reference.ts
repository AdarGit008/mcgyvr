function whole(value: unknown): boolean {
  return typeof value === "number" && Number.isInteger(value);
}

function isRecord(value: unknown): boolean {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function label(value: unknown): boolean {
  return typeof value === "string" && value.length > 0;
}

export function settleSwapRequests(
  board: Record<string, unknown>,
  requests: Record<string, unknown>[],
): Record<string, unknown> {
  if (!isRecord(board)) {
    throw new Error("the board is not a record");
  }
  if (Object.keys(board).sort().join(",") !== "cap,cleared,duties,peak,quota") {
    throw new Error("the board's keys are not exactly the five named");
  }

  const duties = board["duties"];
  if (!Array.isArray(duties)) {
    throw new Error("the duties are not a list");
  }
  const held = new Map<number, Map<string, string>>();
  for (const duty of duties) {
    if (!isRecord(duty)) {
      throw new Error("a duty is not a record");
    }
    if (Object.keys(duty).sort().join(",") !== "day,post,worker") {
      throw new Error("a duty's keys are not exactly the three named");
    }
    const day = duty["day"];
    if (!whole(day) || Number(day) < 1) {
      throw new Error("a day is not whole or falls below one");
    }
    if (!label(duty["post"])) {
      throw new Error("a post is not a non-empty string");
    }
    if (!label(duty["worker"])) {
      throw new Error("a worker is not a non-empty string");
    }
    const posts = held.get(Number(day)) ?? new Map<string, string>();
    if (posts.has(String(duty["post"]))) {
      throw new Error("two duties share one day and post");
    }
    posts.set(String(duty["post"]), String(duty["worker"]));
    held.set(Number(day), posts);
  }
  for (const posts of held.values()) {
    const workers = new Set<string>();
    for (const worker of posts.values()) {
      if (workers.has(worker)) {
        throw new Error("a worker opens on two posts of one day");
      }
      workers.add(worker);
    }
  }

  const cleared = board["cleared"];
  if (!Array.isArray(cleared)) {
    throw new Error("the cleared list is not a list");
  }
  const clearances = new Map<string, Set<string>>();
  for (const entry of cleared) {
    if (!isRecord(entry)) {
      throw new Error("a clearance is not a record");
    }
    if (Object.keys(entry).sort().join(",") !== "posts,worker") {
      throw new Error("a clearance's keys are not exactly the two named");
    }
    if (!label(entry["worker"])) {
      throw new Error("a cleared worker is not a non-empty string");
    }
    if (clearances.has(String(entry["worker"]))) {
      throw new Error("two clearances name one worker");
    }
    const posts = entry["posts"];
    if (!Array.isArray(posts)) {
      throw new Error("a clearance's posts are not a list");
    }
    const set = new Set<string>();
    for (const post of posts) {
      if (!label(post)) {
        throw new Error("a cleared post is not a non-empty string");
      }
      if (set.has(post)) {
        throw new Error("a clearance repeats a post");
      }
      set.add(post);
    }
    clearances.set(String(entry["worker"]), set);
  }
  for (const posts of held.values()) {
    for (const worker of posts.values()) {
      if (!clearances.has(worker)) {
        throw new Error("a worker on duty has no clearance entry");
      }
    }
  }

  const peakList = board["peak"];
  if (!Array.isArray(peakList)) {
    throw new Error("the peak days are not a list");
  }
  const peak = new Set<number>();
  for (const day of peakList) {
    if (!whole(day) || Number(day) < 1) {
      throw new Error("a peak day is not whole or falls below one");
    }
    if (peak.has(Number(day))) {
      throw new Error("a peak day is listed twice");
    }
    peak.add(Number(day));
  }

  const cap = board["cap"];
  if (!whole(cap) || Number(cap) < 0) {
    throw new Error("the cap is not whole or falls below nought");
  }
  const quota = board["quota"];
  if (!whole(quota) || Number(quota) < 0) {
    throw new Error("the quota is not whole or falls below nought");
  }

  if (!Array.isArray(requests)) {
    throw new Error("settleSwapRequests expects a list of requests");
  }
  for (const request of requests) {
    if (!isRecord(request)) {
      throw new Error("a request is not a record");
    }
    if (Object.keys(request).sort().join(",") !== "left,right") {
      throw new Error("a request's keys are not exactly left and right");
    }
    for (const side of [request["left"], request["right"]]) {
      if (!Array.isArray(side) || side.length !== 2) {
        throw new Error("a side is not a list of exactly two entries");
      }
      if (!whole(side[0]) || Number(side[0]) < 1) {
        throw new Error("a side's day is not whole or falls below one");
      }
      if (!label(side[1])) {
        throw new Error("a side's post is not a non-empty string");
      }
    }
  }

  const tally = new Map<string, number>();
  const rulings: string[] = [];

  const owner = (day: number, post: string): string | undefined =>
    held.get(day)?.get(post);

  for (const request of requests) {
    const left = request["left"] as [number, string];
    const right = request["right"] as [number, string];
    const dayLeft = Number(left[0]);
    const postLeft = String(left[1]);
    const dayRight = Number(right[0]);
    const postRight = String(right[1]);
    const one = owner(dayLeft, postLeft);
    const two = owner(dayRight, postRight);

    if (one === undefined || two === undefined) {
      rulings.push("unknown");
      continue;
    }
    if ((dayLeft === dayRight && postLeft === postRight) || one === two) {
      rulings.push("same");
      continue;
    }
    if (!clearances.get(one)!.has(postRight) || !clearances.get(two)!.has(postLeft)) {
      rulings.push("uncleared");
      continue;
    }

    const after = (worker: string): number[] => {
      const days: number[] = [];
      for (const [day, posts] of held) {
        for (const [post, sitting] of posts) {
          let now = sitting;
          if (day === dayLeft && post === postLeft) {
            now = two;
          } else if (day === dayRight && post === postRight) {
            now = one;
          }
          if (now === worker) {
            days.push(day);
          }
        }
      }
      return days;
    };

    const daysOne = after(one);
    const daysTwo = after(two);
    const doubled = (days: number[]): boolean => new Set(days).size !== days.length;
    if (doubled(daysOne) || doubled(daysTwo)) {
      rulings.push("clash");
      continue;
    }
    const heavy = (days: number[]): number => days.filter((day) => peak.has(day)).length;
    if (heavy(daysOne) > Number(cap) || heavy(daysTwo) > Number(cap)) {
      rulings.push("peak");
      continue;
    }
    if ((tally.get(one) ?? 0) >= Number(quota) || (tally.get(two) ?? 0) >= Number(quota)) {
      rulings.push("quota");
      continue;
    }

    held.get(dayLeft)!.set(postLeft, two);
    held.get(dayRight)!.set(postRight, one);
    tally.set(one, (tally.get(one) ?? 0) + 1);
    tally.set(two, (tally.get(two) ?? 0) + 1);
    rulings.push("taken");
  }

  const roster: string[] = [];
  const days = [...held.keys()].sort((a, b) => a - b);
  for (const day of days) {
    const posts = [...held.get(day)!.keys()].sort((a, b) => (a < b ? -1 : a > b ? 1 : 0));
    for (const post of posts) {
      roster.push(`${day} ${post} ${held.get(day)!.get(post)}`);
    }
  }

  return { rulings, roster };
}
