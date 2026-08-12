import assert from "node:assert/strict";
import { auditTicket } from "./solution.ts";

assert.equal(auditTicket("AB-1234-3"), "ok", "a sound ticket passes");
assert.equal(auditTicket("ZZ-0000-2"), "ok", "the heaviest letters with empty digits pass");
assert.equal(auditTicket("AE-4000-0"), "ok", "a total ending in zero wants the digit zero");
assert.equal(auditTicket("AB-1234-7"), "check", "a wrong check digit is named");
assert.equal(auditTicket("ab-1234-3"), "shape", "small letters break the shape");
assert.equal(auditTicket("AB-123-3"), "shape", "too few digits break the shape");
assert.throws(() => auditTicket(42), Error, "a ticket that is not a string is rejected");
console.log("ok");
