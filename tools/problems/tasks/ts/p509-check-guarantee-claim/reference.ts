const SPAN = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];

function span(year: number, month: number): number {
  if (month !== 2) return SPAN[month - 1];
  return year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0) ? 29 : 28;
}

function split(text: unknown): [number, number, number] {
  if (typeof text !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(text)) {
    throw new Error("a day must be written as YYYY-MM-DD");
  }
  const year = Number(text.slice(0, 4));
  const month = Number(text.slice(5, 7));
  const day = Number(text.slice(8, 10));
  if (year < 1900 || year > 2999 || month < 1 || month > 12 || day < 1 || day > span(year, month)) {
    throw new Error("a day must be real and lie in 1900 through 2999");
  }
  return [year, month, day];
}

function serial(year: number, month: number, day: number): number {
  const back = month <= 2 ? year - 1 : year;
  const era = Math.floor(back / 400);
  const yoe = back - era * 400;
  const doy = Math.floor((153 * (month + (month > 2 ? -3 : 9)) + 2) / 5) + day - 1;
  return era * 146097 + yoe * 365 + Math.floor(yoe / 4) - Math.floor(yoe / 100) + doy - 719468;
}

function stamp(count: number): string {
  const shifted = count + 719468;
  const era = Math.floor(shifted / 146097);
  const doe = shifted - era * 146097;
  const yoe = Math.floor(
    (doe - Math.floor(doe / 1460) + Math.floor(doe / 36524) - Math.floor(doe / 146096)) / 365,
  );
  const year = yoe + era * 400;
  const doy = doe - (365 * yoe + Math.floor(yoe / 4) - Math.floor(yoe / 100));
  const mp = Math.floor((5 * doy + 2) / 153);
  const day = doy - Math.floor((153 * mp + 2) / 5) + 1;
  const month = mp + (mp < 10 ? 3 : -9);
  const full = month <= 2 ? year + 1 : year;
  return (
    String(full).padStart(4, "0") +
    "-" +
    String(month).padStart(2, "0") +
    "-" +
    String(day).padStart(2, "0")
  );
}

export function checkGuaranteeClaim(
  sold: string,
  months: number,
  grace: number,
  claim: string,
): Record<string, unknown> {
  const [sy, sm, sd] = split(sold);
  if (typeof months !== "number" || !Number.isInteger(months) || months < 1 || months > 240) {
    throw new Error("months must be a whole number from 1 to 240");
  }
  if (typeof grace !== "number" || !Number.isInteger(grace) || grace < 0 || grace > 365) {
    throw new Error("grace must be a whole number from 0 to 365");
  }
  const [cy, cm, cd] = split(claim);

  const raw = sm + months;
  const year = sy + Math.floor((raw - 1) / 12);
  const month = ((raw - 1) % 12) + 1;
  const plain = serial(year, month, Math.min(sd, span(year, month)));
  const last = plain + grace;
  const start = serial(sy, sm, sd);
  const asked = serial(cy, cm, cd);

  let verdict = "inside";
  if (asked < start) verdict = "early";
  else if (asked > last) verdict = "lapsed";
  else if (asked > plain) verdict = "grace";
  const over = verdict === "lapsed" ? asked - last : 0;

  return { plain: stamp(plain), last: stamp(last), verdict, over };
}
