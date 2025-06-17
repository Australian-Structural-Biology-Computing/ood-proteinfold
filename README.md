# ood-proteinfold (OnDemand App)

`ood-proteinfold` is an [Open OnDemand](https://openondemand.org/) interactive app for computational protein structure prediction using [Proteinfold](https://nf-co.re/proteinfold/) ([AlphaFold2](https://github.com/google-deepmind/alphafold/), [Boltz](https://github.com/jwohlwend/boltz/), [ColabFold](https://github.com/sokrypton/ColabFold), [ESMFold](https://github.com/facebookresearch/esm), and [RoseTTAFold-All-Atom](https://github.com/baker-laboratory/RoseTTAFold-All-Atom/)) originally built for [UNSW's Katana HPC](https://www.unsw.edu.au/research/facilities-and-infrastructure/find-an-instrument/restech-instruments/katana).

## Features

- Predict protein structures from amino acid sequences, FASTA files, or samplesheets.
- Supports multiple prediction methods found within [nf-core/proteinfold](https://nf-co.re/proteinfold/).
- Customisable run parameters via web form.
- Results accessible via web interface.

## Usage

1. **Access**: Launch the app via the Open OnDemand portal.
2. **Input**: Provide a sequence, FASTA directory, or samplesheet.
3. **Configure**: Select prediction method, mode, and database options.
4. **Submit**: Start the job; monitor progress and download results when complete.

## Key Files

- `form.yml.erb`: Defines the web form and input parameters.
- `template/script.sh.erb`: Main job script for running predictions.
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
   - Create `kod_proteinfold-${RUN_ENVIRONMENT}.config` files for proteinfold-specific nextflow configurations. Or remove this line from `script.sh.erb` if not needed.
   - Create a `template/.env` file to change any of these default parameters:

```
# Example .env for ood-proteinfold

# Base output directory for all runs (job-specific OUT_DIR set at runtime)
BASE_OUT_DIR=/srv/scratch/${USER}/proteinfold_output

# Environment (prod, dev, etc.)
RUN_ENVIRONMENT=prod

# Project root: location of Nextflow configs and samplesheet-utils environment
PROJECT_ROOT=/srv/scratch/sbf-pipelines/proteinfold

# Database path for structure prediction modules
DB_PATH=/srv/scratch/sbf-pipelines/proteinfold/dbs

# Git branch to use for proteinfold
BRANCH=master

# Repository path for using alternative versions of proteinfold
REPOSITORY=Australian-Structural-Biology-Computing/proteinfold

# Debug group for permissions on debug files
DEBUGGROUP=sbf-pipelines

# Base debug directory (job-specific DEBUGDIR set at runtime)
BASE_DEBUGDIR=/srv/scratch/sbf/debug

# Nextflow work directory base (job-specific NXF_WORK set at runtime)
BASE_NXF_WORK=/srv/scratch/${USER}/.proteinfold/work

# Apptainer/Singularity blob cache directories (set here or via your institutional Nextflow config, e.g. https://github.com/Australian-Structural-Biology-Computing/unsw_katana)
# APPTAINER_CACHEDIR=/srv/scratch/${USER}/.images
# SINGULARITY_CACHEDIR=/srv/scratch/${USER}/.images

# Nextflow Apptainer/Singularity image cache/library directories (set here or via institutional Nextflow config, e.g. https://github.com/nf-core/configs/blob/master/conf/pipeline/proteinfold/unsw_katana.config)
# NXF_APPTAINER_CACHEDIR=/srv/scratch/${USER}/.images
# NXF_SINGULARITY_CACHEDIR=/srv/scratch/${USER}/.images
# NXF_APPTAINER_LIBRARYDIR=/srv/scratch/sbf-pipelines/proteinfold/singularity
# NXF_SINGULARITY_LIBRARYDIR=/srv/scratch/sbf-pipelines/proteinfold/singularity
```

### Python Environment for samplesheet-utils

`samplesheet-utils` is required for generating and validating input samplesheets.
You must create a Python virtual environment and install the correct version:

```bash
python3 -m venv ${PROJECT_ROOT}/${RUN_ENVIRONMENT}/venv
source ${PROJECT_ROOT}/${RUN_ENVIRONMENT}/venv/bin/activate
pip install samplesheet-utils==1.1.2
```

Update the path in `.env` if your environment is elsewhere.

## Citation

Please cite [doi.org/10.26190/4KQF-M552](https://doi.org/10.26190/4KQF-M552) and acknowledge the Structural Biology Facility at UNSW in publications.

---
For support, please open an issue.
