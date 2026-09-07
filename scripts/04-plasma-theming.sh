#!/usr/bin/env bash
# Stage 04: Apply KDE Plasma 6 Customizations
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
source "${SCRIPT_DIR}/lib/common.sh"

DRY_RUN=false
EXTRA_ARGS=()
for arg in "$@"; do
    if [[ "$arg" == "--dry-run" || "$arg" == "-n" ]]; then
        DRY_RUN=true
        EXTRA_ARGS+=("--dry-run")
    fi
done

log_info "Stage 04: Applying KDE Plasma 6 customizations..."

if [[ -d "${REPO_ROOT}/plasma/configs" ]] && [[ -n "$(ls -A "${REPO_ROOT}/plasma/configs" 2>/dev/null)" ]]; then
    bash "${REPO_ROOT}/plasma/restore-kde.sh" "${EXTRA_ARGS[@]}"
else
    log_info "No saved Plasma configs found in plasma/configs/ yet."
    log_info "To capture your current setup, run: bash plasma/backup-kde.sh"
fi

log_success "Stage 04 complete."
