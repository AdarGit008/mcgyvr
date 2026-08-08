function whole(value: unknown): boolean {
  return typeof value === "number" && Number.isInteger(value);
}

function isRecord(value: unknown): boolean {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function label(value: unknown): boolean {
  return typeof value === "string" && value.length > 0;
}

export function auditSwapBoard(
  board: Record<string, unknown>,
  ceiling: number,
): Record<string, unknown> {
  if (!whole(ceiling) || ceiling < 1) {
    throw new Error("the ceiling is not whole or falls below one");
  }
  if (!isRecord(board)) {
    throw new Error("the board is not a record");
  }
  if (Object.keys(board).sort().join(",") !== "claims,shifts") {
    throw new Error("the board's keys are not exactly shifts and claims");
  }

  const shifts = board["shifts"];
  if (!Array.isArray(shifts)) {
    throw new Error("the shifts are not a list");
  }
  const days = new Map<string, number>();
  const holders = new Map<string, string>();
  for (const shift of shifts) {
    if (!isRecord(shift)) {
      throw new Error("a shift is not a record");
    }
    if (Object.keys(shift).sort().join(",") !== "code,day,holder") {
      throw new Error("a shift's keys are not exactly the three named");
    }
    if (!label(shift["code"])) {
      throw new Error("a code is not a non-empty string");
    }
    if (holders.has(String(shift["code"]))) {
      throw new Error("two shifts carry one code");
    }
    const day = shift["day"];
    if (!whole(day) || Number(day) < 1 || Number(day) > 7) {
      throw new Error("a day is not whole or falls outside one through seven");
    }
    if (!label(shift["holder"])) {
      throw new Error("a holder is not a non-empty string");
    }
    days.set(String(shift["code"]), Number(day));
    holders.set(String(shift["code"]), String(shift["holder"]));
  }

  const claims = board["claims"];
  if (!Array.isArray(claims)) {
    throw new Error("the claims are not a list");
  }
  for (const claim of claims) {
    if (!isRecord(claim)) {
      throw new Error("a claim is not a record");
    }
    if (Object.keys(claim).sort().join(",") !== "bidder,code") {
      throw new Error("a claim's keys are not exactly code and bidder");
    }
    if (!label(claim["code"])) {
      throw new Error("a claimed code is not a non-empty string");
    }
    if (!label(claim["bidder"])) {
      throw new Error("a bidder is not a non-empty string");
    }
  }

  const moved = new Set<string>();
  const verdicts: string[] = [];

  for (const claim of claims) {
    const code = String(claim["code"]);
    const bidder = String(claim["bidder"]);
    if (!holders.has(code)) {
      verdicts.push("unknown");
      continue;
    }
    if (moved.has(code)) {
      verdicts.push("gone");
      continue;
    }
    if (holders.get(code) === bidder) {
      verdicts.push("self");
      continue;
    }
    let clash = false;
    let load = 0;
    for (const [other, who] of holders) {
      if (who !== bidder) {
        continue;
      }
      load++;
      if (days.get(other) === days.get(code)) {
        clash = true;
      }
    }
    if (clash) {
      verdicts.push("busy");
      continue;
    }
    if (load >= ceiling) {
      verdicts.push("full");
      continue;
    }
    holders.set(code, bidder);
    moved.add(code);
    verdicts.push("taken");
  }

  const counts = new Map<string, number>();
  for (const who of holders.values()) {
    counts.set(who, (counts.get(who) ?? 0) + 1);
  }
  const loads = [...counts.keys()]
    .sort((a, b) => (a < b ? -1 : a > b ? 1 : 0))
    .map((who) => `${who} ${counts.get(who)}`);

  return { verdicts, loads };
}
