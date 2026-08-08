function isRecord(value: unknown): boolean {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isWhole(value: unknown): boolean {
  return typeof value === "number" && Number.isInteger(value);
}

export function checkLoadManifest(items: any[], plan: any): any {
  if (!isRecord(plan)) {
    throw new Error("plan must be a record");
  }
  if (!Array.isArray(plan.zones) || plan.zones.length === 0) {
    throw new Error("plan.zones must be a list holding at least one zone");
  }
  const caps = new Map<string, number>();
  const arms = new Map<string, number>();
  const order: string[] = [];
  for (const zone of plan.zones) {
    if (!isRecord(zone)) {
      throw new Error("each zone must be a record");
    }
    if (typeof zone.zone !== "string" || zone.zone.length === 0) {
      throw new Error("a zone name must be a non-empty string");
    }
    if (caps.has(zone.zone)) {
      throw new Error(`two zones answer to the name ${zone.zone}`);
    }
    if (!isWhole(zone.cap) || zone.cap < 1) {
      throw new Error("a cap must be a whole number above nought");
    }
    if (!isWhole(zone.arm)) {
      throw new Error("an arm must be a whole number");
    }
    caps.set(zone.zone, zone.cap);
    arms.set(zone.zone, zone.arm);
    order.push(zone.zone);
  }
  if (!isWhole(plan.gross) || plan.gross < 1) {
    throw new Error("gross must be a whole number above nought");
  }
  if (!isWhole(plan.low) || !isWhole(plan.high)) {
    throw new Error("low and high must be whole numbers");
  }
  if (plan.low > plan.high) {
    throw new Error("low must be no greater than high");
  }

  if (!Array.isArray(items)) {
    throw new Error("items must be a list");
  }
  const seen = new Set<string>();
  const manifest: { tag: string; zone: string; mass: number }[] = [];
  for (const item of items) {
    if (!isRecord(item)) {
      throw new Error("each item must be a record");
    }
    if (typeof item.tag !== "string" || item.tag.length === 0) {
      throw new Error("tag must be a non-empty string");
    }
    if (seen.has(item.tag)) {
      throw new Error(`two items answer to the tag ${item.tag}`);
    }
    seen.add(item.tag);
    if (typeof item.zone !== "string" || item.zone.length === 0) {
      throw new Error("an item's zone must be a non-empty string");
    }
    if (!caps.has(item.zone)) {
      throw new Error(`the plan names no zone called ${item.zone}`);
    }
    if (!isWhole(item.mass) || item.mass < 1) {
      throw new Error("mass must be a whole number above nought");
    }
    manifest.push({ tag: item.tag, zone: item.zone, mass: item.mass });
  }

  const perZone = new Map<string, number>();
  for (const name of order) {
    perZone.set(name, 0);
  }
  const loaded: string[] = [];
  let mass = 0;
  let moment = 0;
  let stopped = "";
  let limit = "";
  for (const item of manifest) {
    const zoneMass = perZone.get(item.zone) + item.mass;
    const holdMass = mass + item.mass;
    const swing = moment + item.mass * arms.get(item.zone);
    if (zoneMass > caps.get(item.zone)) {
      limit = "cap";
    } else if (holdMass > plan.gross) {
      limit = "gross";
    } else if (swing < plan.low || swing > plan.high) {
      limit = "moment";
    }
    if (limit !== "") {
      stopped = item.tag;
      break;
    }
    perZone.set(item.zone, zoneMass);
    mass = holdMass;
    moment = swing;
    loaded.push(item.tag);
  }

  return {
    loaded,
    stopped,
    limit,
    mass,
    moment,
    zones: order.map((name) => ({ zone: name, mass: perZone.get(name) })),
  };
}
