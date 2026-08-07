const MODES = ["dark", "live", "ramp"];

function record(value: any): boolean {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function text(value: any): boolean {
  return typeof value === "string" && value.length > 0;
}

function whole(value: any): boolean {
  return typeof value === "number" && Number.isInteger(value);
}

function owns(holder: any, key: string): boolean {
  return Object.prototype.hasOwnProperty.call(holder, key);
}

function roster(value: any, label: string): Set<string> {
  if (!Array.isArray(value)) {
    throw new Error(label + " must be a list");
  }
  const held = new Set<string>();
  for (const id of value) {
    if (!text(id)) {
      throw new Error(label + " must hold non-empty strings");
    }
    if (held.has(id)) {
      throw new Error(label + " names " + id + " twice");
    }
    held.add(id);
  }
  return held;
}

export function decideSwitch(
  setting: any,
  caller: any,
): { open: string; why: string } {
  if (
    !record(setting) ||
    !owns(setting, "mode") ||
    !owns(setting, "barred") ||
    !owns(setting, "waved") ||
    !owns(setting, "cutoff")
  ) {
    throw new Error("a setting must carry mode, barred, waved and cutoff");
  }
  if (!MODES.includes(setting.mode)) {
    throw new Error("mode must be dark, live or ramp");
  }
  const barred = roster(setting.barred, "barred");
  const waved = roster(setting.waved, "waved");
  for (const id of barred) {
    if (waved.has(id)) {
      throw new Error(id + " is both barred and waved");
    }
  }
  if (!whole(setting.cutoff) || setting.cutoff < 0 || setting.cutoff > 100) {
    throw new Error("cutoff must be a whole number from 0 to 100");
  }
  if (!record(caller) || !owns(caller, "id") || !owns(caller, "slot")) {
    throw new Error("a caller must be a record carrying id and slot");
  }
  if (!text(caller.id)) {
    throw new Error("id must be a non-empty string");
  }
  if (!whole(caller.slot) || caller.slot < 0 || caller.slot > 99) {
    throw new Error("slot must be a whole number from 0 to 99");
  }

  if (barred.has(caller.id)) {
    return { open: "no", why: "barred" };
  }
  if (setting.mode === "dark") {
    return { open: "no", why: "dark" };
  }
  if (waved.has(caller.id)) {
    return { open: "yes", why: "waved" };
  }
  if (setting.mode === "live") {
    return { open: "yes", why: "live" };
  }
  if (caller.slot < setting.cutoff) {
    return { open: "yes", why: "ramp" };
  }
  return { open: "no", why: "held" };
}
