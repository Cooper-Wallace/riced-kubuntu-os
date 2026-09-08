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
    spin_task "Configuring Flathub remote repository" \
        flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo

    FLATPAK_LIST="${REPO_ROOT}/manifests/flatpaks.list"
    if [[ -f "${FLATPAK_LIST}" ]]; then
        mapfile -t FLATPAKS < <(grep -vE '^\s*(#|$)' "${FLATPAK_LIST}" || true)
        for app in "${FLATPAKS[@]}"; do
            if flatpak info "$app" >/dev/null 2>&1; then
                log_success "Flatpak ${app} is already installed."
            else
                spin_task "Installing Flatpak: ${app}" \
                    bash -c "flatpak install -y --non-interactive flathub '${app}' < /dev/null"
            fi
        done
    fi
else
    log_warn "Flatpak is not installed. Skipping flatpak packages."
fi

# Snap setup
SNAP_LIST="${REPO_ROOT}/manifests/snaps.list"
if [[ -f "${SNAP_LIST}" ]] && check_cmd snap; then
    mapfile -t SNAPS < <(grep -vE '^\s*(#|$)' "${SNAP_LIST}" || true)
    for snap_item in "${SNAPS[@]}"; do
        if snap list "$snap_item" >/dev/null 2>&1; then
            log_success "Snap ${snap_item} is already installed."
        else
            spin_task "Installing Snap: ${snap_item}" sudo snap install "${snap_item}"
        fi
    done
fi

log_success "Stage 02 complete."
