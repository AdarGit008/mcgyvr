import assert from "node:assert/strict";
import { openWindows } from "./solution.ts";

assert.equal(openWindows("09:00-17:00", ["09:00-12:00"]), "12:00-17:00", "an appointment at the opening pushes the first free stretch later");
assert.equal(openWindows("09:00-17:00", ["10:00-11:00"]), "09:00-10:00, 11:00-17:00", "an appointment in the middle splits the day in two");
assert.equal(openWindows("08:30-09:45", []), "08:30-09:45", "an empty book leaves the whole span free");
assert.equal(openWindows("09:00-17:00", ["13:00-14:00", "10:00-11:00"]), "09:00-10:00, 11:00-13:00, 14:00-17:00", "appointments are placed in time order however they arrive");
assert.equal(openWindows("09:00-12:00", ["09:00-10:00", "10:00-11:00"]), "11:00-12:00", "appointments that meet exactly leave nothing between them");
assert.equal(openWindows("09:00-11:00", ["09:00-10:00", "10:00-11:00"]), "none", "a span covered end to end reports none");
assert.throws(() => openWindows("09:00-17:00", ["9:00-10:00"]), Error, "an appointment without a two-digit hour is rejected");
console.log("ok");
