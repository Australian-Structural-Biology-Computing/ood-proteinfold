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
  commandPreviewArguments,
  formatShellArgument,
  methodPreviewArguments,
  sampleIdForInput
} = require("../form.js");

const pairs = (argumentsList) => Object.fromEntries(
  Array.from({ length: argumentsList.length / 2 }, (_, index) =>
    argumentsList.slice(index * 2, index * 2 + 2)
  )
);

assert.deepEqual(
  pairs(methodPreviewArguments({
    af_method: "alphafold2",
    full_dbs: "full",
    random_seed: "42"
  })),
  {
    "--mode": "alphafold2",
    "--full_dbs": "true",
    "--random_seed": "42"
  }
);

assert.deepEqual(
  pairs(methodPreviewArguments({
    af_method: "boltz",
    random_seed: "7",
    boltz_use_potentials: true
  })),
  {
    "--mode": "boltz",
    "--random_seed": "7",
    "--boltz_use_potentials": "true"
  }
);

assert.deepEqual(
  pairs(methodPreviewArguments({ af_method: "alphafold3", af3_weights: "/weights.bin" })),
  { "--mode": "alphafold3", "--alphafold3_params_path": "/weights.bin" }
);

assert.deepEqual(
  pairs(methodPreviewArguments({
    af_method: "esmfold",
    esmfold_num_recycles: "8",
    save_intermediates: true
  })),
  {
    "--mode": "esmfold",
    "--esmfold_num_recycles": "8",
    "--save_intermediates": "true"
  }
);

assert.deepEqual(
  pairs(methodPreviewArguments({
    af_method: "colabfold",
    random_seed: "11",
    colabfold_num_recycles: "6",
    colabfold_advanced_options: true
  })),
  {
    "--mode": "colabfold",
    "--random_seed": "11",
    "--colabfold_num_recycles": "6",
    "--save_intermediates": "true"
  }
);

assert.deepEqual(
  commandPreviewArguments({
    user: "z1234567",
    samplesheet: "/data/samplesheet.csv",
    run_name: "ESM run",
    af_method: "esmfold",
    esmfold_num_recycles: "1"
  }),
  [
    "nextflow",
    "-c", "/srv/scratch/sbf-pipelines/proteinfold/kod_proteinfold-dev.config",
    "run", "Australian-Structural-Biology-Computing/proteinfold",
    "-r", "master",
    "-latest",
    "--input", "/data/samplesheet.csv",
    "--outdir", "/srv/scratch/z1234567/proteinfold_output/ESM_run",
    "--db", "/srv/scratch/sbf-pipelines/proteinfold/proteinfold_microdbs",
    "--mode", "esmfold",
    "--esmfold_num_recycles", "1",
    "--use_gpu", "--monochrome_logs",
    "-profile", "apptainer"
  ]
);

assert.equal(sampleIdForInput({ sampleId: "sheet-id", label: "ignored.fasta" }), "sheet-id");
assert.equal(sampleIdForInput({ manualSequence: "ACDEFGHIK" }), "ACDEFG");
assert.equal(sampleIdForInput({ label: "my protein.fasta" }), "my-protein");
assert.equal(formatShellArgument("--esmfold_num_recycles"), "--esmfold_num_recycles");
assert.equal(formatShellArgument("/path/with\\_underscores/file.csv"), "/path/with_underscores/file.csv");
assert.equal(formatShellArgument("run with spaces"), "'run with spaces'");
assert.equal(formatShellArgument("${USER}"), '"${USER}"');

console.log("form.js focused tests passed");
