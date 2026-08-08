type Stop = { name: string; walk: number; stay: number; worth: number };

function whole(value: unknown): boolean {
  return typeof value === "number" && Number.isInteger(value);
}

export function planExhibitTour(
  stops: Record<string, unknown>[],
  budget: number,
): { names: string[]; worth: number; minutes: number } {
  if (!Array.isArray(stops)) {
    throw new Error("planExhibitTour expects a list of stops");
  }
  if (!whole(budget) || budget < 0) {
    throw new Error("the budget is not whole or falls below nought");
  }

  const halls: Stop[] = [];
  const seen = new Set<string>();
  for (const stop of stops) {
    if (typeof stop !== "object" || stop === null || Array.isArray(stop)) {
      throw new Error("a stop is not a mapping");
    }
    if (Object.keys(stop).sort().join(",") !== "name,stay,walk,worth") {
      throw new Error("a stop's keys are not exactly the four named");
    }
    const name = stop["name"];
    if (typeof name !== "string" || name.length === 0) {
      throw new Error("a name is not a non-empty string");
    }
    if (seen.has(name)) {
      throw new Error("a name is repeated");
    }
    seen.add(name);
    const walk = stop["walk"];
    if (!whole(walk) || (walk as number) < 0) {
      throw new Error("a walk is not whole or falls below nought");
    }
    const stay = stop["stay"];
    if (!whole(stay) || (stay as number) < 1) {
      throw new Error("a stay is not whole or falls below one");
    }
    const worth = stop["worth"];
    if (!whole(worth) || (worth as number) < 0) {
      throw new Error("a worth is not whole or falls below nought");
    }
    halls.push({
      name,
      walk: walk as number,
      stay: stay as number,
      worth: worth as number,
    });
  }

  const reach: number[] = [];
  let paced = 0;
  for (const hall of halls) {
    paced += hall.walk;
    reach.push(paced);
  }

  const worthOf = (picks: number[]): number => {
    let total = 0;
    for (const index of picks) {
      total += halls[index].worth;
    }
    return total;
  };

  // Same last stop and same total stay means the same minutes, so only
  // worth, then count, then the picks themselves decide a cell.
  const finer = (left: number[], right: number[]): boolean => {
    const a = worthOf(left);
    const b = worthOf(right);
    if (a !== b) {
      return a > b;
    }
    if (left.length !== right.length) {
      return left.length < right.length;
    }
    for (let k = 0; k < left.length; k++) {
      if (left[k] !== right[k]) {
        return left[k] < right[k];
      }
    }
    return false;
  };

  const states: Map<number, number[]>[] = halls.map(() => new Map());
  for (let i = 0; i < halls.length; i++) {
    const offer = (stayTotal: number, picks: number[]): void => {
      if (reach[i] + stayTotal > budget) {
        return;
      }
      const held = states[i].get(stayTotal);
      if (held === undefined || finer(picks, held)) {
        states[i].set(stayTotal, picks);
      }
    };
    offer(halls[i].stay, [i]);
    for (let j = 0; j < i; j++) {
      for (const [stayTotal, picks] of states[j]) {
        offer(stayTotal + halls[i].stay, [...picks, i]);
      }
    }
  }

  let bestPicks: number[] = [];
  let bestWorth = 0;
  let bestMinutes = 0;
  for (let i = 0; i < halls.length; i++) {
    for (const [stayTotal, picks] of states[i]) {
      const worth = worthOf(picks);
      const minutes = reach[i] + stayTotal;
      let wins = false;
      if (worth !== bestWorth) {
        wins = worth > bestWorth;
      } else if (minutes !== bestMinutes) {
        wins = minutes < bestMinutes;
      } else if (picks.length !== bestPicks.length) {
        wins = picks.length < bestPicks.length;
      } else {
        for (let k = 0; k < picks.length; k++) {
          if (picks[k] !== bestPicks[k]) {
            wins = picks[k] < bestPicks[k];
            break;
          }
        }
      }
      if (wins) {
        bestPicks = picks;
        bestWorth = worth;
        bestMinutes = minutes;
      }
    }
  }

  return {
    names: bestPicks.map((index) => halls[index].name),
    worth: bestWorth,
    minutes: bestMinutes,
  };
}
