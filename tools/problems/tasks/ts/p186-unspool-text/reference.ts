export function unspoolText(spool: string): string {
  if (typeof spool !== "string") {
    throw new Error("spool must be a string");
  }
  let out = "";
  let at = 0;
  while (at < spool.length) {
    const ch = spool[at];
    if (ch !== "<") {
      out += ch;
      at += 1;
      continue;
    }
    if (spool[at + 1] === "<") {
      out += "<";
      at += 2;
      continue;
    }
    const close = spool.indexOf(">", at + 1);
    if (close === -1) {
      throw new Error("pointer whose greater-than sign never arrives");
    }
    const body = spool.slice(at + 1, close);
    const comma = body.indexOf(",");
    if (comma === -1) {
      throw new Error("pointer with no comma in it");
    }
    const fields = [body.slice(0, comma), body.slice(comma + 1)];
    for (const field of fields) {
      if (!/^\d+$/.test(field)) {
        throw new Error("pointer field is not digits");
      }
      if (field.length > 1 && field[0] === "0") {
        throw new Error("pointer field carries a padding zero");
      }
      if (Number(field) === 0) {
        throw new Error("pointer field is zero");
      }
    }
    const reach = Number(fields[0]);
    const haul = Number(fields[1]);
    if (reach > out.length) {
      throw new Error("reach is larger than what has been produced");
    }
    for (let taken = 0; taken < haul; taken += 1) {
      out += out[out.length - reach];
    }
    at = close + 1;
  }
  return out;
}
