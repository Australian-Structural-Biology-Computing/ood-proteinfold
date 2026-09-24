"use strict";

const assert = require("node:assert/strict");

global.document = {
  addEventListener() {},
  querySelectorAll() { return []; },
  querySelector() { return null; },
  getElementById() { return null; }
};
global.window = {};

const {
  outputLocations,
  sampleIdForInput,
  uniqueSampleIds
} = require("../form.js");

assert.equal(sampleIdForInput({ sampleId: "sheet-id", label: "ignored.fasta" }), "sheet-id");
assert.equal(sampleIdForInput({ manualSequence: "ACDEFGHIK" }), "ACDEFG");
assert.equal(sampleIdForInput({ label: "my protein.fasta" }), "my_protein");
assert.equal(
  sampleIdForInput({ collectionInput: true, label: "my protein.v1.fasta" }),
  "my-protein_v1"
);
assert.deepEqual(
  uniqueSampleIds([
    { sampleId: "protein" },
    { sampleId: "protein" },
    { label: "protein.fasta" }
  ]),
  ["protein", "protein-2", "protein-3"]
);

assert.deepEqual(
  outputLocations("/outputs", "my run", "alphafold2", ["sample"])[0],
  {
    sampleId: "sample",
    sampleDirectory: "/outputs/my_run/alphafold2/split_msa_prediction",
    sampleEntry: "sample",
    structuresDirectory: "/outputs/my_run/alphafold2/split_msa_prediction/top_ranked_structures",
    structureEntry: "sample.pdb"
  }
);
assert.equal(
  outputLocations("/outputs/", "my run", "boltz", ["sample"])[0].structureEntry,
  "sample.cif"
);

console.log("form.js collision helper tests passed");
