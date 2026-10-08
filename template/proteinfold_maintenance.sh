function proteinfold_maintenance_log() { printf '[ProteinFold maintenance] %s\n' "$*" >>"${DEBUG_LOG}"; }
PROTEINFOLD_QUARANTINE_DIR="${BASE_OUT_DIR}/QUARANTINE"
PROTEINFOLD_MAINTENANCE_LOCK="${BASE_NXF_WORK}/.quarantine.lock"
[[ "$(realpath -m -- "${BASE_NXF_WORK}")" == "/srv/scratch/${USER}/.proteinfold/work" && "$(realpath -m -- "${BASE_OUT_DIR}")" == "/srv/scratch/${USER}/proteinfold_output" ]] || return 0

function proteinfold_run_locked() {
    { ( flock -n 9 || exit 0; "$@" ) 9>>"${PROTEINFOLD_MAINTENANCE_LOCK}"; } >>"${DEBUG_LOG}" 2>&1
}
function proteinfold_read_scratch_quota() {
    /usr/lpp/mmfs/bin/mmlsquota -Y -j "user_${USER}" kura_rfs2 2>/dev/null |
        awk -F: -v fileset="user_${USER}" '
            $3 == 0 && $10 == fileset && $13 > 0 && $18 > 0 { print $11, $13, $16, $18; found = 1; exit }
            END { exit !found }'
}
function proteinfold_report_quota() {
    local phase="$1" quota="$2" block_usage block_limit file_usage file_limit
    local block_tenths file_tenths remaining
    [[ -n "${quota}" ]] || return 0
    read -r block_usage block_limit file_usage file_limit <<<"${quota}" || return 0

    if [[ -n "${METRICS_FILE}" && -f "${METRICS_FILE}" ]]; then
        jq --arg phase "${phase}" --argjson block_usage_kib "${block_usage}" \
            --argjson block_limit_kib "${block_limit}" --argjson files_usage "${file_usage}" \
            --argjson files_limit "${file_limit}" \
            '.scratch_quota[$phase] = {block_usage_kib: $block_usage_kib,
            block_limit_kib: $block_limit_kib, files_usage: $files_usage,
            files_limit: $files_limit, block_percent: ((1000 * $block_usage_kib / $block_limit_kib | round) / 10),
            files_percent: ((1000 * $files_usage / $files_limit | round) / 10)}' \
            "${METRICS_FILE}" >"${METRICS_FILE}.maintenance.tmp" &&
            mv "${METRICS_FILE}.maintenance.tmp" "${METRICS_FILE}" || true
    fi

    [[ "${phase}" == finish ]] || return 0
    ((100 * block_usage > 80 * block_limit || 100 * file_usage > 80 * file_limit)) || return 0
    block_tenths=$(((2000 * block_usage + block_limit) / (2 * block_limit)))
    file_tenths=$(((2000 * file_usage + file_limit) / (2 * file_limit)))
    remaining=$((file_limit - file_usage))
    ((remaining > 0)) || remaining=0
    printf '\n===============================================================\n'
    printf 'WARNING: Your scratch space is more than 80%% full.\n'
    if ((100 * block_usage > 80 * block_limit)); then
        printf 'Storage usage: %d.%d%%\n' "$((block_tenths / 10))" "$((block_tenths % 10))"
    fi
    if ((100 * file_usage > 80 * file_limit)); then
        printf 'File count usage: %d.%d%% (%d files/folders remaining)\n' \
            "$((file_tenths / 10))" "$((file_tenths % 10))" "${remaining}"
        printf 'Scratch limits both storage and the number of files and folders.\n'
        printf 'Large collections of small files can reach the file-count limit.\n'
    fi
    printf 'Future jobs may fail unless unneeded scratch files are removed.\n'
    printf '===============================================================\n\n'
}
function proteinfold_quarantine_old_work() {
    local run_dir run_dir_mtime activity_mtime name destination moved=0 cutoff lease_cutoff
    cutoff=$(date -d '90 days ago' +%s) || return 1
    lease_cutoff=$(date -d '2 days ago' +%s) || return 1

    if [[ "$(stat -c %d "${BASE_NXF_WORK}")" != "$(stat -c %d "${BASE_OUT_DIR}")" ]]; then
        proteinfold_maintenance_log "Work and output directories are on different filesystems; skipping quarantine."
        return 0
    fi

    while IFS= read -r -d '' run_dir; do
        run_dir_mtime=$(stat -c %Y "${run_dir}" 2>/dev/null) || continue
        if [[ -e "${run_dir}/launch/.nextflow/history" ]]; then
            activity_mtime=$(stat -c %Y "${run_dir}/launch/.nextflow/history" 2>/dev/null) || continue
            ((activity_mtime > run_dir_mtime)) && run_dir_mtime=${activity_mtime}
        fi
        ((run_dir_mtime <= cutoff)) || continue
        if [[ -e "${run_dir}/.active" ]]; then
            activity_mtime=$(stat -c %Y "${run_dir}/.active" 2>/dev/null) || continue
            ((activity_mtime <= lease_cutoff)) || continue
        fi
        name=${run_dir##*/}
        destination="${PROTEINFOLD_QUARANTINE_DIR}/${name}"
        [[ ! -e "${destination}" ]] || continue
        mkdir -p "${PROTEINFOLD_QUARANTINE_DIR}" || return 1
        if touch "${run_dir}/.quarantined-at" && mv -- "${run_dir}" "${destination}"; then
            moved=$((moved + 1))
        else
            rm -f -- "${run_dir}/.quarantined-at" || true
        fi
    done < <(find "${BASE_NXF_WORK}" -mindepth 1 -maxdepth 1 -type d \
        ! -path "${RUN_STATE_DIR}" ! -newermt "@${cutoff}" -print0)
    ((moved == 0)) || proteinfold_maintenance_log "Moved ${moved} old ProteinFold run directories to ${PROTEINFOLD_QUARANTINE_DIR}."
}
function proteinfold_delete_expired_quarantine() {
    local marker directory cutoff
    local -a expired=()
    [[ -d "${PROTEINFOLD_QUARANTINE_DIR}" ]] || return 0
    cutoff=$(date -d '14 days ago' +%s) || return 1
    while IFS= read -r -d '' marker; do
        expired+=("${marker%/.quarantined-at}")
        ((${#expired[@]} >= 6)) && break
    done < <(find "${PROTEINFOLD_QUARANTINE_DIR}" -mindepth 2 -maxdepth 2 -type f \
        -name .quarantined-at ! -newermt "@${cutoff}" -print0)
    ((${#expired[@]} > 0)) || return 0

    if timeout 5m rm -rf -- "${expired[@]}"; then
        proteinfold_maintenance_log "Removed ${#expired[@]} expired quarantined work directories."
    else
        for directory in "${expired[@]}"; do
            if [[ -d "${directory}" ]]; then
                touch -d '1970-01-01 UTC' "${directory}/.quarantined-at" 2>/dev/null || true
            fi
        done
        proteinfold_maintenance_log "Deletion of expired quarantined work did not finish; a future run will continue it."
    fi
}
function proteinfold_same_directory() {
    [[ -d "${1:-}" && -d "${2:-}" ]] || return 1
    [[ "$(stat -L -c '%d:%i' -- "${1}")" == "$(stat -L -c '%d:%i' -- "${2}")" ]]
}
function proteinfold_cleanup_container_cache() {
    local cache_dir apptainer_cache image
    cache_dir=${NXF_APPTAINER_CACHEDIR:-${APPTAINER_CACHEDIR:-}}
    if [[ -n "${cache_dir}" && -d "${cache_dir}" ]]; then
        cache_dir=$(realpath -m -- "${cache_dir}")
        if [[ "${cache_dir}" == "/srv/scratch/${USER}/"* ]] &&
            ! proteinfold_same_directory "${cache_dir}" "${NXF_APPTAINER_LIBRARYDIR:-}" &&
            ! proteinfold_same_directory "${cache_dir}" "${NXF_SINGULARITY_LIBRARYDIR:-}"; then
            while IFS= read -r -d '' image; do
                if [[ -n "${NXF_APPTAINER_LIBRARYDIR:-}" && -f "${NXF_APPTAINER_LIBRARYDIR}/${image##*/}" ]] ||
                    [[ -n "${NXF_SINGULARITY_LIBRARYDIR:-}" && -f "${NXF_SINGULARITY_LIBRARYDIR}/${image##*/}" ]]; then
                    rm -f -- "${image}" || true
                fi
            done < <(find "${cache_dir}" -mindepth 1 -maxdepth 1 -type f \
                \( -name '*.img' -o -name '*.sif' \) -print0)
        fi
    fi

    apptainer_cache=${APPTAINER_CACHEDIR:-${SINGULARITY_CACHEDIR:-}}
    if [[ -n "${apptainer_cache}" && -d "${apptainer_cache}" ]]; then
        apptainer_cache=$(realpath -m -- "${apptainer_cache}")
        if [[ "${apptainer_cache}" == "/srv/scratch/${USER}/"* ]]; then
            timeout 5m apptainer cache clean --days 90 \
                --type blob,oci,oras,library,shub,net --force ||
                proteinfold_maintenance_log "Apptainer cache cleanup did not finish; a future run will retry it."
        fi
    fi
}
function proteinfold_maintenance_exit() {
    local exit_status="$1" quota_at_finish=""
    trap - EXIT
    rm -f -- "${RUN_STATE_DIR}/.active" || true
    if [[ "${exit_status}" -eq 0 ]]; then
        proteinfold_run_locked proteinfold_cleanup_container_cache || true
        proteinfold_run_locked proteinfold_delete_expired_quarantine || true
    fi

    quota_at_finish=$(proteinfold_read_scratch_quota) || true
    proteinfold_report_quota start "${PROTEINFOLD_QUOTA_AT_START}" || true
    proteinfold_report_quota finish "${quota_at_finish}" || true
    write_completion_metrics "${exit_status}"
}

{
    mkdir -p "${BASE_NXF_WORK}" "${RUN_STATE_DIR}" || true
    touch "${RUN_STATE_DIR}" "${RUN_STATE_DIR}/.active" || true
    PROTEINFOLD_QUOTA_AT_START=$(proteinfold_read_scratch_quota) || true
    proteinfold_run_locked proteinfold_quarantine_old_work ||
        proteinfold_maintenance_log "Old work quarantine failed; continuing."
} >>"${DEBUG_LOG}" 2>&1
trap 'proteinfold_maintenance_exit "$?"' EXIT
