#!/usr/bin/env bash
# Stage 00: Configure Package Repositories and PPAs
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
source "${SCRIPT_DIR}/lib/common.sh"

DRY_RUN=false
for arg in "$@"; do
    [[ "$arg" == "--dry-run" || "$arg" == "-n" ]] && DRY_RUN=true
done

log_info "Stage 00: Checking and applying software repositories..."
PPA_LIST="${REPO_ROOT}/manifests/ppas.list"

if [[ -f "${PPA_LIST}" ]]; then
    while IFS= read -r line || [[ -n "$line" ]]; do
        [[ -z "$line" || "$line" =~ ^# ]] && continue
        log_info "Configuring repository: ${line}"
        if [[ "$line" =~ ^ppa: ]]; then
            run_safe sudo add-apt-repository -y "$line"
        fi
    done < "${PPA_LIST}"
fi

run_safe sudo apt update -y
log_success "Stage 00 complete."
