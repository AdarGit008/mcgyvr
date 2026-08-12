/** Name the first fault a depot ticket carries, or call it ok. */

const ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";

export function auditTicket(ticket: string): string {
  if (typeof ticket !== "string") {
    throw new Error("auditTicket expects a string");
  }
  if (!/^[A-Z]{2}-\d{4}-\d$/.test(ticket)) {
    return "shape";
  }
  const [prefix, run, check] = ticket.split("-");
  let total = 0;
  for (const letter of prefix) {
    total += ALPHABET.indexOf(letter) + 1;
  }
  for (let spot = 0; spot < run.length; spot++) {
    total += Number(run[spot]) * (spot + 1);
  }
  if (total % 10 !== Number(check)) {
    return "check";
  }
  return "ok";
}
