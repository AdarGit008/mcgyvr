const MARKS = "!#$%&*+-?@";
const CLASSES = ["lower", "upper", "digit", "mark"];

function classOf(ch: string): string {
  if (ch >= "a" && ch <= "z") return "lower";
  if (ch >= "A" && ch <= "Z") return "upper";
  if (ch >= "0" && ch <= "9") return "digit";
  if (MARKS.includes(ch)) return "mark";
  return "";
}

function whole(value: any): boolean {
  return typeof value === "number" && Number.isInteger(value) && value >= 1;
}

export function reportSecretFaults(phrase: string, policy: any): string[] {
  if (typeof phrase !== "string") {
    throw new Error("the phrase must be a string");
  }
  if (policy === null || typeof policy !== "object" || Array.isArray(policy)) {
    throw new Error("the policy must be a record");
  }
  for (const key of ["least", "most", "needs", "forbidden"]) {
    if (!(key in policy)) {
      throw new Error("the policy is missing " + key);
    }
  }
  if (!whole(policy.least) || !whole(policy.most)) {
    throw new Error("least and most must be whole numbers of one or more");
  }
  if (policy.most < policy.least) {
    throw new Error("most may not fall below least");
  }
  if (!Array.isArray(policy.needs) || policy.needs.length === 0) {
    throw new Error("needs must be a non-empty list");
  }
  const wanted: string[] = [];
  for (const name of policy.needs) {
    if (!CLASSES.includes(name)) {
      throw new Error("needs names a class outside the four");
    }
    if (wanted.includes(name)) {
      throw new Error("needs names one class twice");
    }
    wanted.push(name);
  }
  if (!Array.isArray(policy.forbidden)) {
    throw new Error("forbidden must be a list");
  }
  for (const word of policy.forbidden) {
    if (typeof word !== "string" || !/^[a-z]+$/.test(word)) {
      throw new Error("a forbidden word must be small letters only");
    }
  }

  const faults: string[] = [];
  if (phrase.length < policy.least) faults.push("short");
  if (phrase.length > policy.most) faults.push("long");
  const found = new Set<string>();
  let stray = false;
  for (const ch of phrase) {
    const kind = classOf(ch);
    if (kind === "") stray = true;
    else found.add(kind);
  }
  if (stray) faults.push("stray");
  for (const name of CLASSES) {
    if (wanted.includes(name) && !found.has(name)) faults.push(name);
  }
  const lowered = phrase.toLowerCase();
  if (policy.forbidden.some((word: string) => lowered.includes(word))) {
    faults.push("forbidden");
  }
  return faults;
}
