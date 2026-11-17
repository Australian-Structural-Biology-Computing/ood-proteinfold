#!/bin/bash
#
# Provision ColabFold2 model weights for the single-workflow proteinfold
# pipeline into a shared weights root.
#
# The weights root layout matches the pipeline's PREPARE_COLABFOLD2_DBS
# expectations:
#
#   <root>/params/af3/libcifpp/components.cif          shared CCD components
#   <root>/params/af3/<model>/<model>.bin.zst          AF3-family checkpoints
#   <root>/params/af3/<model>/download_<model>_fp32<r>_finished.txt
#   <root>/params/params_model_*.npz                   AlphaFold2 checkpoints
#
# Point the pipeline at it with --colabfold2_params_path <root> (the OOD app's
# "Model Weights Directory" field), or symlink it as
# <DB_PATH>/colabfold2_models so the pipeline's implicit fallback finds it.
#
# Blobs are fetched with curl on the host (the HuggingFace CDN is fast, while
# the container's own single-stream downloader can be orders of magnitude
# slower), then validated by the container's ensure_weights, which resolves the
# expected per-model file set (including companions such as the ESMFold2 LM
# shim) and would fetch anything missing itself.
#
# Usage:
#   scripts/provision_colabfold2_params.sh [WEIGHTS_ROOT]
#
# Environment overrides:
#   IMAGE   container image to use
#           (default: the shared af3-preview ColabFold image)
#   MODELS  space-separated list of AF3-family backends to download
#           (default: all backends exposed by the app; fp32 precision)

set -euo pipefail

WEIGHTS_ROOT="${1:-/srv/scratch/sbf-pipelines/proteinfold/colabfold2_params}"
IMAGE="${IMAGE:-/srv/scratch/sbf-pipelines/containers/ghcr.io-jscgh-proteinfold_colabfold-af3-preview-e9e8bd0.img}"
MODELS="${MODELS:-alphafold3 boltz2 chai1 protenix2 openfold3 openbind0 intellifold2 opendde rosettafold3 esmfold2}"
# Leave this much free in the target fileset before starting each download.
MIN_FREE_GB="${MIN_FREE_GB:-10}"

mkdir -p "${WEIGHTS_ROOT}"
WEIGHTS_ROOT=$(realpath "${WEIGHTS_ROOT}")

free_gb() {
    df --output=avail -BG "$(dirname "${WEIGHTS_ROOT}")" | tail -1 | tr -dc '0-9'
}

check_space() {
    local avail
    avail=$(free_gb)
    if (( avail < MIN_FREE_GB )); then
        echo "ERROR: only ${avail}G free under ${WEIGHTS_ROOT}; aborting before it fills." >&2
        exit 1
    fi
}

run_python() {
    apptainer exec --cleanenv --bind /srv/scratch "${IMAGE}" python3
}

# Revision-qualified completion markers used by the pipeline to detect
# complete (non-stale) weights: chai1 r3, boltz2 r1, others unqualified.
marker_revision() {
    case "$1" in
        chai1)  echo "_r3" ;;
        boltz2) echo "_r1" ;;
        *)      echo "" ;;
    esac
}

echo "Weights root: ${WEIGHTS_ROOT}"
echo "Container:    ${IMAGE}"
echo "Free space:   $(free_gb)G"

for model in ${MODELS}; do
    revision=$(marker_revision "${model}")
    marker="${WEIGHTS_ROOT}/params/af3/${model}/download_${model}_fp32${revision}_finished.txt"
    if [[ -f "${marker}" ]]; then
        echo "[skip] ${model} already provisioned (${marker})"
        continue
    fi
    check_space

    # 1. Resolve the model's expected blob set and pre-seed any missing files
    #    with curl on the host. urllib-free and resumable via --retry.
    run_python <<PY > "${WEIGHTS_ROOT}/.fetch_${model}.tsv"
from pathlib import Path
from alphafold3.model import model_registry
from colabfold.alphafold3 import weights as cw
spec = model_registry.get("${model}")
target = cw.model_dir_for(spec.name, Path("${WEIGHTS_ROOT}"), "fp32")
for path, filename in cw._wanted(spec, "fp32"):
    print(cw.urls_for(path, spec.weights_repo)[0] + "\t" + str(target / filename))
PY
    mkdir -p "${WEIGHTS_ROOT}/params/af3/${model}"
    while IFS=$'\t' read -r url dest; do
        if [[ -s "${dest}" ]]; then
            echo "  [have] $(basename "${dest}")"
            continue
        fi
        echo "  [curl] $(basename "${dest}")"
        curl -L --fail --silent --show-error --retry 3 -o "${dest}" "${url}"
    done < "${WEIGHTS_ROOT}/.fetch_${model}.tsv"
    rm -f "${WEIGHTS_ROOT}/.fetch_${model}.tsv"

    # 2. Let the container validate the layout and fetch anything the curl
    #    pass could not (its ensure_weights skips files already present).
    #    accept_terms covers models published under their own terms (currently
    #    only Google DeepMind's alphafold3); provisioning assumes the facility
    #    operates under those terms, as surfaced by the app's AlphaFold3
    #    warning at submission time.
    echo "  [validate] ${model}"
    run_python <<PY
from pathlib import Path
from colabfold.alphafold3.models import ensure_weights
from colabfold.alphafold3.weights import ensure_ccd
root = Path("${WEIGHTS_ROOT}")
ensure_ccd(root)
ensure_weights("${model}", data_dir=root, precision="fp32", download=True, accept_terms=True)
PY

    # ensure_weights returns early without writing a marker when the blobs are
    # already in place, so make the completion marker explicit.
    test -f "${marker}" || touch "${marker}"
    test -f "${WEIGHTS_ROOT}/params/af3/libcifpp/components.cif"
    echo "[done] ${model}"
done

# AlphaFold2 uses ColabFold's own parameter layout (params/params_model_*.npz);
# the plain alphafold2 mode token needs both the ptm and multimer_v3 parameter
# sets so colabfold_batch can pick per query.
if [[ -f "${WEIGHTS_ROOT}/params/download_finished.txt" && -f "${WEIGHTS_ROOT}/params/download_complexes_multimer_v3_finished.txt" ]]; then
    echo "[skip] alphafold2 parameters already present"
else
    check_space
    echo "[download] alphafold2 (alphafold2_ptm + alphafold2_multimer_v3)"
    run_python <<PY
from pathlib import Path
from colabfold.download import download_alphafold_params
root = Path("${WEIGHTS_ROOT}")
for variant in ("alphafold2_ptm", "alphafold2_multimer_v3"):
    download_alphafold_params(variant, data_dir=root)
PY
    echo "[done] alphafold2"
fi

echo "All requested weights provisioned under ${WEIGHTS_ROOT}"
du -sh "${WEIGHTS_ROOT}"
