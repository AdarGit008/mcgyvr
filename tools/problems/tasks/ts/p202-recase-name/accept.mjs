import assert from "node:assert/strict";
import { recaseName } from "./solution.ts";

assert.equal(recaseName("parseURL", "snake"), "parse_url", "trailing acronym goes small");
assert.equal(recaseName("XMLHTTPRequest", "kebab"), "xmlhttp-request", "run hands over its last capital");
assert.equal(recaseName("utf8Frame", "snake"), "utf_8_frame", "a digit run is its own word");
assert.equal(recaseName("base64Value", "shout"), "BASE_64_VALUE", "shout uppercases every word");
assert.equal(recaseName("http-probe-id", "pascal"), "HttpProbeId", "hyphens are word ends");
assert.equal(recaseName("parse_url", "camel"), "parseUrl", "small words stay small in camel");
assert.equal(recaseName("parseURL", "camel"), "parseURL", "an acronym keeps its capitals in camel");
assert.equal(recaseName("parseURL", "pascal"), "ParseURL", "an acronym keeps its capitals in pascal");
assert.equal(recaseName("HTTP", "camel"), "http", "the opening word is wholly small in camel");
assert.equal(recaseName("HTTP", "pascal"), "HTTP", "a lone acronym survives pascal");
assert.equal(recaseName("id", "kebab"), "id", "one word needs no joiner");
assert.equal(recaseName("ABc", "snake"), "a_bc", "a two capital run splits before a small letter");
assert.equal(recaseName("readXML2Frame", "kebab"), "read-xml-2-frame", "digits break an acronym");
assert.deepEqual(
  ["snake", "kebab", "shout", "pascal", "camel"].map((style) => recaseName("PDF_reportV2", style)),
  ["pdf_report_v_2", "pdf-report-v-2", "PDF_REPORT_V_2", "PDFReportV2", "pdfReportV2"],
  "every style reads the same cut",
);
assert.throws(() => recaseName("", "snake"), Error, "an empty label is rejected");
assert.throws(() => recaseName("_lead", "snake"), Error, "a leading separator is rejected");
assert.throws(() => recaseName("trail-", "snake"), Error, "a trailing separator is rejected");
assert.throws(() => recaseName("two__gaps", "snake"), Error, "a doubled separator is rejected");
assert.throws(() => recaseName("dot.name", "snake"), Error, "a stray character is rejected");
assert.throws(() => recaseName("fine", "title"), Error, "an unknown style is rejected");
assert.throws(() => recaseName(42, "snake"), Error, "a non-string label is rejected");
assert.throws(() => recaseName("fine", null), Error, "a non-string style is rejected");
console.log("ok");
