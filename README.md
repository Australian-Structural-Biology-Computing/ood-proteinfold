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

2. **Configure for your site**:
   - Copy `.env.example` to `template/.env`.
   - Adjust the environment variables in `template/.env` for your cluster, queue, paths, email defaults, and output locations.
   - If needed, set `PFOLD_NEXTFLOW_CONFIG` to your institutional Nextflow config file instead of editing `script.sh.erb`.

```
# Example template/.env for ood-proteinfold

OOD_CLUSTER=katana
OOD_QUEUE=submission
PFOLD_SCRIPT_FILE=/srv/scratch/sbf-pipelines/proteinfold/bin/start-alphafold2.sh
OOD_EMAIL_DOMAIN=@example.edu
PFOLD_NATIVE_DEFAULT=-A my_project;-l select=1:ncpus=2:mem=4gb;-l walltime=48:00:00
PFOLD_NATIVE_GPU=-l select=1:ncpus=8:ngpus=1:mem=124gb;-l walltime=12:00:00
PFOLD_RUN_ENVIRONMENT=prod
PFOLD_PROJECT_ROOT=/apps/proteinfold
PFOLD_DB_PATH=/data/proteinfold/dbs
PFOLD_BRANCH=master
PFOLD_REPOSITORY=Australian-Structural-Biology-Computing/proteinfold
PFOLD_NEXTFLOW_CONFIG=/apps/proteinfold/kod_proteinfold-prod.config
PFOLD_BASE_OUT_DIR=/scratch/${USER}/proteinfold_output
PFOLD_BASE_NXF_WORK=/scratch/${USER}/.proteinfold/work
OOD_RESULTS_URL_BASE=/pun/sys/dashboard/files/fs
```

### Python Environment for samplesheet-utils

`samplesheet-utils` is required for generating and validating input samplesheets.
You must create a Python virtual environment and install the correct version:

```bash
python3 -m venv ${PROJECT_ROOT}/${RUN_ENVIRONMENT}/venv
source ${PROJECT_ROOT}/${RUN_ENVIRONMENT}/venv/bin/activate
pip install samplesheet-utils==1.1.2
```

Prefer changing `template/.env` over editing the app templates directly so upgrades stay easy to rebase across institutions.

## Citation

Please cite [doi.org/10.26190/4KQF-M552](https://doi.org/10.26190/4KQF-M552) and acknowledge the Structural Biology Facility at UNSW in publications.

---
For support, please open an issue.
