"use strict";

const assert = require("node:assert/strict");

global.document = {
  addEventListener() {},
  querySelectorAll() { return []; },
  querySelector() { return null; },
  getElementById() { return null; }
};
global.window = {};

const { commandPreviewArguments, formatShellArgument, methodPreviewArguments } = require("../form.js");

assert.deepEqual(
  methodPreviewArguments({
    af_method: "alphafold2", proteinfold_version: "release", prot_mode: "multimer",
    full_dbs: "full", random_seed: "42"
  }),
  [
    "--mode", "alphafold2", "--alphafold2_db", "/srv/scratch/sbf-pipelines/proteinfold/dbs",
    "--alphafold2_full_dbs", "true", "--alphafold2_mode", "split_msa_prediction",
    "--random_seed", "42", "--alphafold2_model_preset", "multimer"
  ]
);

assert.deepEqual(
  commandPreviewArguments({
    user: "z1234567", proteinfold_version: "release", samplesheet: "/data/samplesheet.csv",
    run_name: "ESM run", af_method: "esmfold", prot_mode: "monomer_ptm",
    esmfold_num_recycles: "1"
  }),
  [
    "nextflow", "-c", "/srv/scratch/sbf-pipelines/proteinfold/kod_proteinfold-prod.config",
    "run", "nf-core/proteinfold", "-r", "2.0.0", "-latest",
    "--input", "/data/samplesheet.csv",
    "--outdir", "/srv/scratch/z1234567/proteinfold_output/ESM_run",
    "--mode", "esmfold", "--esmfold_db", "/srv/scratch/sbf-pipelines/proteinfold/dbs",
    "--esmfold_model_preset", "monomer_ptm", "--esmfold_num_recycles", "1",
    "--use_gpu", "--monochrome_logs", "-profile", "apptainer"
  ]
);

assert.equal(formatShellArgument("run with spaces"), "'run with spaces'");
assert.equal(formatShellArgument("${USER}"), '"${USER}"');

console.log("form.js command preview tests passed");
