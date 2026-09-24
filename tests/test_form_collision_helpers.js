"use strict";

const assert = require("node:assert/strict");

global.document = {
  addEventListener() {},
  querySelectorAll() { return []; },
  querySelector() { return null; },
  getElementById() { return null; }
};
global.window = {};

const { sampleIdForInput } = require("../form.js");

assert.equal(sampleIdForInput({ sampleId: "sheet-id", label: "ignored.fasta" }), "sheet-id");
assert.equal(sampleIdForInput({ manualSequence: "ACDEFGHIK" }), "ACDEFG");
assert.equal(sampleIdForInput({ label: "my protein.fasta" }), "my-protein");

console.log("form.js collision helper tests passed");
