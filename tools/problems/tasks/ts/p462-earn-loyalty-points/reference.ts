type Rung = { from: number; per: number };

function whole(value: unknown): boolean {
  return typeof value === "number" && Number.isInteger(value);
}

export function earnLoyaltyPoints(
  receipts: number[],
  ladder: Record<string, unknown>[],
): number[] {
  if (!Array.isArray(receipts) || !Array.isArray(ladder)) {
    throw new Error("earnLoyaltyPoints expects two lists");
  }
  if (ladder.length === 0) {
    throw new Error("the ladder carries no rungs");
  }
  const rungs: Rung[] = [];
  for (const entry of ladder) {
    if (typeof entry !== "object" || entry === null || Array.isArray(entry)) {
      throw new Error("a rung is not a mapping");
    }
    const keys = Object.keys(entry).sort();
    if (keys.length !== 2 || keys[0] !== "from" || keys[1] !== "per") {
      throw new Error("a rung carries exactly from and per");
    }
    const from = entry["from"];
    const per = entry["per"];
    if (!whole(from) || Number(from) < 0) {
      throw new Error("a rung's from is not whole or falls below nought");
    }
    if (!whole(per) || Number(per) < 0) {
      throw new Error("a rung's per is not whole or falls below nought");
    }
    rungs.push({ from: Number(from), per: Number(per) });
  }
  if (rungs[0].from !== 0) {
    throw new Error("the opening rung does not sit at nought");
  }
  for (let i = 1; i < rungs.length; i++) {
    if (rungs[i].from <= rungs[i - 1].from) {
      throw new Error("the from values fail to climb strictly");
    }
  }
  for (const receipt of receipts) {
    if (!whole(receipt) || Number(receipt) < 0) {
      throw new Error("a receipt is not whole or falls below nought");
    }
  }

  const awards: number[] = [];
  let outlay = 0;
  for (const receipt of receipts) {
    let per = rungs[0].per;
    for (const rung of rungs) {
      if (rung.from <= outlay) {
        per = rung.per;
      }
    }
    awards.push(Math.floor((receipt * per) / 1000));
    outlay += receipt;
  }
  return awards;
}
