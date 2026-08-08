type Parcel = {
  name: string;
  mass: number;
  bears: number;
  high: number;
  wide: number;
  top: boolean;
};

function whole(value: unknown): boolean {
  return typeof value === "number" && Number.isInteger(value);
}

export function stackPallet(
  items: any[],
  limits: any,
): { stacked: string[]; refused: string; reason: string; mass: number; high: number } {
  if (!Array.isArray(items)) {
    throw new Error("items must be a list");
  }
  if (limits === null || typeof limits !== "object" || Array.isArray(limits)) {
    throw new Error("limits must be a record");
  }
  for (const key of ["deck", "roof"]) {
    if (!whole(limits[key]) || limits[key] < 1) {
      throw new Error(`${key} must be a whole number above nought`);
    }
  }

  const named = new Set<string>();
  const parcels: Parcel[] = [];
  for (const item of items) {
    if (item === null || typeof item !== "object" || Array.isArray(item)) {
      throw new Error("an item must be a record");
    }
    if (typeof item.name !== "string" || item.name.length === 0) {
      throw new Error("a name must be a non-empty string");
    }
    if (named.has(item.name)) {
      throw new Error(`two items answer to the name ${item.name}`);
    }
    named.add(item.name);
    if (!whole(item.mass) || item.mass < 1) {
      throw new Error("a mass must be a whole number above nought");
    }
    if (!whole(item.bears) || item.bears < 0) {
      throw new Error("bears must be a whole number of nought or more");
    }
    if (!whole(item.high) || item.high < 1) {
      throw new Error("high must be a whole number above nought");
    }
    if (!whole(item.wide) || item.wide < 1) {
      throw new Error("wide must be a whole number above nought");
    }
    if (typeof item.top !== "boolean") {
      throw new Error("top must be either true or false");
    }
    parcels.push({
      name: item.name,
      mass: item.mass,
      bears: item.bears,
      high: item.high,
      wide: item.wide,
      top: item.top,
    });
  }

  const stacked: string[] = [];
  const placed: Parcel[] = [];
  let mass = 0;
  let high = 0;
  for (const parcel of parcels) {
    const under = placed.length > 0 ? placed[placed.length - 1] : null;
    let reason = "";
    if (under !== null && under.top) {
      reason = "capped";
    } else if (under !== null && parcel.wide > under.wide) {
      reason = "overhang";
    } else {
      let load = parcel.mass;
      for (let i = placed.length - 1; i >= 0; i--) {
        if (load > placed[i].bears) {
          reason = "crush";
          break;
        }
        load += placed[i].mass;
      }
    }
    if (reason === "" && mass + parcel.mass > limits.deck) {
      reason = "deck";
    }
    if (reason === "" && high + parcel.high > limits.roof) {
      reason = "roof";
    }
    if (reason !== "") {
      return { stacked, refused: parcel.name, reason, mass, high };
    }
    stacked.push(parcel.name);
    placed.push(parcel);
    mass += parcel.mass;
    high += parcel.high;
  }
  return { stacked, refused: "", reason: "", mass, high };
}
