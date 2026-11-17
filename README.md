# ood-proteinfold (OnDemand App)

`ood-proteinfold` is an [Open OnDemand](https://openondemand.org/) interactive app for computational protein structure prediction using the single-workflow [Proteinfold](https://nf-co.re/proteinfold/) pipeline (AlphaFold2, AlphaFold3, Boltz2, ESMFold2 and the other [ColabFold2](https://github.com/sokrypton/ColabFold) backends: Chai1, Protenix2, OpenFold3, OpenBind0, IntelliFold2, OpenDDE and RosettaFold3) originally built for [UNSW's Katana HPC](https://www.unsw.edu.au/research/facilities-and-infrastructure/find-an-instrument/restech-instruments/katana).

> This branch (`single-workflow`) targets the `single-workflow` branch of the proteinfold pipeline, where `--mode` selects a ColabFold2 backend (all structure prediction runs through the pipeline's `COLABFOLD2_INFERENCE` process) and `--msa_tool` selects the MSA generator. The app exposes all three generators — ColabFold search (MMseqs2), the AlphaFold2 pipeline (JackHMMER/hhblits) and the AlphaFold3 data pipeline — selectable independently for every method, defaulting to the fast MMseqs2 search.

## Features

- Predict protein structures from amino acid sequences, FASTA files, or samplesheets.
- Supports AlphaFold2, AlphaFold3, Boltz2, ESMFold2 and the additional ColabFold2 backends through the single-workflow pipeline.
- Optional conformational sampling (seed count, dropout, MSA depth) available for every method.
- MSA generation selectable per run: ColabFold search (MMseqs2), the AlphaFold2 pipeline, or the AlphaFold3 data pipeline.
- Customisable run parameters via web form.
- Results accessible via web interface.
- Optionally generates pLDDT-coloured mugshot images for final/top-ranked structures (see [pLDDT mugshot images](#plddt-mugshot-images)).

## Usage

1. **Access**: Launch the app via the Open OnDemand portal.
2. **Input**: Provide a sequence, FASTA directory, or samplesheet.
3. **Configure**: Select prediction method, mode, and database options.
4. **Submit**: Start the job; monitor progress and download results when complete.

## Key Files

- `form.yml.erb`: Defines the web form and input parameters.
- `template/script.sh.erb`: Main job script for running predictions.
- `template/sanitise_input.py`: Validates and normalises staged FASTA and samplesheet inputs.
- `template/protein_mugshots.py`: Optional batch renderer for pLDDT mugshot images and the standalone gallery.
- `template/pae_mugshots.py`: Renders PAE plots from the published `*_pae.tsv` files; used by `protein_mugshots.py`.
- `submit.yml.erb`: Job submission configuration.
- `info.html.erb`: Displays result links after job completion.
- `.github/workflows/`: CI/CD deployment workflows.

## Installation / Implementation

To deploy ProteinFold on your own Open OnDemand instance:

1. **Clone this repository** into your OnDemand apps directory:
   ```bash
   git clone https://github.com/Australian-Structural-Biology-Computing/ood-proteinfold.git /var/www/ood/apps/sys/kod-proteinfold
   ```

2. **Edit files to match institutional settings**:
   - Update `submit.yml.erb` with your facility-specific settings.
   - Change the cluster in `form.yml.erb` to match your HPC.
   - Create `kod_proteinfold-${RUN_ENVIRONMENT}.config` files for proteinfold-specific nextflow configurations. The single-workflow-adapted UNSW Katana profile is maintained as `infra_katana.config` alongside this app; deploy it to `${PROJECT_ROOT}/kod_proteinfold-prod.config`. Or remove this line from `script.sh.erb` if not needed.
   - Create a `template/.env` file to change any of these default parameters:

```
# Example .env for ood-proteinfold

# Base output directory for all runs (job-specific OUT_DIR set at runtime)
BASE_OUT_DIR=/srv/scratch/${USER}/proteinfold_output

# Environment name (e.g., prod, dev)
RUN_ENVIRONMENT=prod

# Project root: location of Nextflow configs and samplesheet-utils environment
PROJECT_ROOT=/srv/scratch/sbf-pipelines/proteinfold

# Database path for structure prediction modules
DB_PATH=/srv/scratch/sbf-pipelines/proteinfold/dbs

# The single-workflow pipeline expects, under DB_PATH: the ColabFold search
# databases (colabfold_envdb/, colabfold_uniref30/), the AlphaFold2 MSA
# databases (for the alphafold2_msa generator), the AlphaFold3 data-pipeline
# databases (for alphafold3_msa), plus a colabfold2_models/ directory holding
# the ColabFold2 model weights (params/af3/<model> layout) for every exposed
# backend.
# Katana compute nodes have no outbound network access, so the weights must be
# provisioned there in advance, or supplied per run via the app's optional
# "Model Weights Directory" field (--colabfold2_params_path).

# Local staged deployment. Leave REVISION empty when PROJECT is a local path.
PROJECT=${PROJECT_ROOT}/releases/current
REVISION=

# Remote deployment alternative:
# PROJECT=nf-core/proteinfold
# REVISION=2.0.0

# Debug group for permissions on debug files
DEBUGGROUP=sbf-pipelines

# Base debug directory (job-specific DEBUGDIR set at runtime)
BASE_DEBUGDIR=/srv/scratch/sbf/debug

# Address emailed only when the failure handler captures a failed run: app,
# user zID, run, exit code, failing line/command/call stack, PBS resources,
# debug path and Files-app link,
# session ID and the tail of debug.log. Defaults to sbf@unsw.edu.au; set empty
# to disable.
FAILURE_EMAIL=sbf@unsw.edu.au

# OnDemand base URL used for links in the failure email
#OOD_BASE_URL=https://kod.restech.unsw.edu.au

# The email is sent with msmtp directly through the UNSW relay, because compute
# nodes have no msmtp config for mail(1). It uses STARTTLS on port 25 and falls
# back to plain text if TLS fails. Override if needed; send errors are logged to
# <debug dir>/failure-email.log.
#SMTP_HOST=smtp.unsw.edu.au
#SMTP_CA_FILE=/etc/pki/tls/certs/ca-bundle.crt
#FAILURE_EMAIL_FROM=<zID>@ad.unsw.edu.au

# Nextflow state directory base. Each new OOD launch gets a timestamped
# subdirectory containing persistent launch/cache, work, and prepared input
# state; OOD Relaunch reuses that subdirectory and enables Nextflow -resume.
BASE_NXF_WORK=/srv/scratch/${USER}/.proteinfold/work

# Apptainer/Singularity blob cache directories (set here or via your institutional Nextflow config, e.g. https://github.com/Australian-Structural-Biology-Computing/unsw_katana)
# APPTAINER_CACHEDIR=/srv/scratch/${USER}/.images
# SINGULARITY_CACHEDIR=/srv/scratch/${USER}/.images

# Nextflow Apptainer/Singularity image cache/library directories (set here or via institutional Nextflow config, e.g. https://github.com/nf-core/configs/blob/master/conf/pipeline/proteinfold/unsw_katana.config)
# NXF_APPTAINER_CACHEDIR=/srv/scratch/${USER}/.images
# NXF_SINGULARITY_CACHEDIR=/srv/scratch/${USER}/.images
# NXF_APPTAINER_LIBRARYDIR=/srv/scratch/sbf-pipelines/containers
# NXF_SINGULARITY_LIBRARYDIR=/srv/scratch/sbf-pipelines/containers
```

If a run is interrupted, use **Relaunch** from its Open OnDemand job card. This
reuses the saved samplesheet and Nextflow state and starts Nextflow with
`-resume`. Relaunch is available only while the original job card remains in
Open OnDemand, so retry the run before the card expires. Do not start a new job
with the same options to resume it: a new submission has different Nextflow
state and is checked as a new run. Nextflow skips tasks already completed in
its saved state and reruns failed or incomplete tasks.

### pLDDT mugshot images

When the default-enabled **Generate pLDDT Mugshot Images** option is selected, `template/protein_mugshots.py` finds supported structures directly inside `top_ranked_structures/` directories after a successful run and writes a three-panel 1200×400 PNG beside each one. Names use `<structure-stem>_plddt_mugshot.png`, with deterministic suffixes for collisions. Colours follow the AlphaFold pLDDT bands: ≥90 `#0053D6`, 70–<90 `#65CBF3`, 50–<70 `#FFDB13`, and <50 `#FF7D45`.

One headless Apptainer/PyMOL process renders the whole run; one host ImageMagick process composes the panels and creates quality-90 WebP previews. `<OUT_DIR>/mugshots/mugshot_index.html` embeds those previews as a standalone gallery, while `mugshot_manifest.tsv` records outcomes. Failures remain non-fatal. Existing non-empty PNGs are reused. PyMOL uses the CPUs allocated by PBS. The host requires ImageMagick with WebP support.

After loading a structure, PyMOL checks that its atom `b` values are numeric, non-constant, and use the 0–100 pLDDT scale before colouring it.

Set `SHARED_CONTAINER_DIR` to the shared container library and provision the pinned image once; runtime jobs never pull from the network:

```bash
MUGSHOT_IMAGE="${SHARED_CONTAINER_DIR}/jysgro-pymol-3.1.0-amd64-ab2facf7869c.sif"
apptainer pull "${MUGSHOT_IMAGE}" \
    docker://jysgro/pymol@sha256:ab2facf7869c4f06c924c287e8ccca127da21fa8954539e1a8e6bfde3128eca5
sha256sum "${MUGSHOT_IMAGE}"
# Expected: 36c541702e06f76212de78af601386355cc3fc4148342221235c481b347bce31
```

Set the deployed image path in `template/.env` when it differs from the default:

```bash
MUGSHOT_RENDERER_IMAGE="${SHARED_CONTAINER_DIR}/jysgro-pymol-3.1.0-amd64-ab2facf7869c.sif"
```

### PAE plots

`template/pae_mugshots.py` draws a 400×400 PAE plot for each structure in `top_ranked_structures/`, shown to the right of its mugshot in the gallery. It reads the lowest-ranked-number `<id>_<rank>_pae.tsv` from `<method>/<id>/paes/` (for AlphaFold2, `alphafold2/<mode>/<id>/paes/`), the matrix published for the top-ranked model, and writes `<structure-stem>_pae.png` beside the structure. The plot uses the AlphaFold database green scale, 0–30 Å, and needs only the Python standard library. Structures without a usable PAE file (for example ESMFold, monomer runs, or empty files) simply show no plot, and `mugshot_manifest.tsv` records `pae_status`. A plot is redrawn when its TSV is newer. The script can also run alone: `python3 pae_mugshots.py --out-dir <OUT_DIR>`.

### Python Environment for samplesheet-utils

`samplesheet-utils` is required for generating and validating input samplesheets.
You must create a Python virtual environment and install the correct version:

```bash
python3 -m venv ${PROJECT_ROOT}/${RUN_ENVIRONMENT}/venv
source ${PROJECT_ROOT}/${RUN_ENVIRONMENT}/venv/bin/activate
pip install samplesheet-utils==1.3.4
```

Update the paths in `.env` if your environment is elsewhere.

## Citation

Please cite [doi.org/10.26190/4KQF-M552](https://doi.org/10.26190/4KQF-M552) and acknowledge the Structural Biology Facility at UNSW in publications.

---
For support, please open an issue.
