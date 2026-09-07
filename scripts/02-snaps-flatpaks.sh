#!/usr/bin/env bash
# Stage 02: Install Flatpak & Snap Applications
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
source "${SCRIPT_DIR}/lib/common.sh"

DRY_RUN=false
for arg in "$@"; do
    [[ "$arg" == "--dry-run" || "$arg" == "-n" ]] && DRY_RUN=true
done

log_info "Stage 02: Installing Flatpak and Snap applications..."

# Flatpak setup (Flathub repository)
if check_cmd flatpak; then
    log_info "Ensuring Flathub remote is configured..."
    run_safe flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo || true

    FLATPAK_LIST="${REPO_ROOT}/manifests/flatpaks.list"
    if [[ -f "${FLATPAK_LIST}" ]]; then
        while IFS= read -r app || [[ -n "$app" ]]; do
            [[ -z "$app" || "$app" =~ ^# ]] && continue
            log_info "Installing Flatpak: ${app}"
            run_safe flatpak install -y flathub "$app"
        done < "${FLATPAK_LIST}"
    fi
else
    log_warn "Flatpak is not installed. Skipping flatpak packages."
fi

# Snap setup
SNAP_LIST="${REPO_ROOT}/manifests/snaps.list"
if [[ -f "${SNAP_LIST}" ]] && check_cmd snap; then
    while IFS= read -r snap_item || [[ -n "$snap_item" ]]; do
        [[ -z "$snap_item" || "$snap_item" =~ ^# ]] && continue
        log_info "Installing Snap: ${snap_item}"
        run_safe sudo snap install ${snap_item}
    done < "${SNAP_LIST}"
fi

log_success "Stage 02 complete."
