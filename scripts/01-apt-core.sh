#!/usr/bin/env bash
# Stage 01: Install Base APT Packages
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
source "${SCRIPT_DIR}/lib/common.sh"

DRY_RUN=false
for arg in "$@"; do
    [[ "$arg" == "--dry-run" || "$arg" == "-n" ]] && DRY_RUN=true
done

log_info "Stage 01: Installing core APT packages..."
APT_LIST="${REPO_ROOT}/manifests/apt-packages.list"

PACKAGES=()
if [[ -f "${APT_LIST}" ]]; then
    while IFS= read -r line || [[ -n "$line" ]]; do
        [[ -z "$line" || "$line" =~ ^# ]] && continue
        PACKAGES+=("$line")
    done < "${APT_LIST}"
fi

if [[ ${#PACKAGES[@]} -gt 0 ]]; then
    log_info "Installing ${#PACKAGES[@]} packages..."
    run_safe sudo apt install -y "${PACKAGES[@]}"
else
    log_warn "No packages found in ${APT_LIST}."
fi

log_success "Stage 01 complete."
