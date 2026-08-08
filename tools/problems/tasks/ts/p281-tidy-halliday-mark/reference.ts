export function tidyShelfMark(raw: string): string {
  if (typeof raw !== "string") {
    throw new Error("a mark must be a string");
  }
  const parts = raw.split("-").map((part) => part.trim());
  if (parts.length !== 3) {
    throw new Error("a mark carries exactly three parts");
  }
  const [wingRaw, bayRaw, pegRaw] = parts;
  if (!/^[A-Za-z]{2}$/.test(wingRaw)) {
    throw new Error("the wing is exactly two letters");
  }
  const bayFound = /^(\d{1,6})(?:\.(\d{1,4}))?$/.exec(bayRaw);
  if (bayFound === null) {
    throw new Error("the bay is misshapen");
  }
  const whole = Number(bayFound[1]);
  if (whole < 1 || whole > 999) {
    throw new Error("the bay stands between 1 and 999");
  }
  let fraction = bayFound[2] ?? "";
  while (fraction.endsWith("0")) {
    fraction = fraction.slice(0, fraction.length - 1);
  }
  if (fraction.length > 2) {
    throw new Error("the fraction is two digits at most");
  }
  const pegFound = /^([A-Za-z])([1-9])$/.exec(pegRaw);
  if (pegFound === null) {
    throw new Error("the peg is one letter with one non-zero digit");
  }
  const bay = fraction.length === 0 ? String(whole) : String(whole) + "." + fraction;
  return (
    wingRaw.toUpperCase() +
    "-" +
    bay +
    "-" +
    pegFound[1].toLowerCase() +
    pegFound[2]
  );
}
