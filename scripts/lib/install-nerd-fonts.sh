#!/usr/bin/env bash
# ==============================================================================
# install-nerd-fonts.sh - Idempotent JetBrains Mono Nerd Font installer
# ==============================================================================
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"

DRY_RUN=false
for arg in "$@"; do
    [[ "$arg" == "--dry-run" || "$arg" == "-n" ]] && DRY_RUN=true
done

FONT_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/fonts/NerdFonts/JetBrainsMono"
VERSION="v3.3.0"
URL="https://github.com/ryanoasis/nerd-fonts/releases/download/${VERSION}/JetBrainsMono.tar.xz"

# Check if font files already exist
if [[ -d "${FONT_DIR}" ]] && compgen -G "${FONT_DIR}/*.ttf" >/dev/null; then
    log_info "JetBrains Mono Nerd Font is already installed at ${FONT_DIR}. Skipping."
    exit 0
fi

log_info "Installing JetBrains Mono Nerd Font (${VERSION})..."

if [[ "${DRY_RUN}" == "true" ]]; then
    log_dry "curl -sSL '${URL}' -o '<temp>/JetBrainsMono.tar.xz'"
    log_dry "tar -xf '<temp>/JetBrainsMono.tar.xz' -C '${FONT_DIR}'"
    log_dry "fc-cache -f '${FONT_DIR}'"
    exit 0
fi

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "${TMP_DIR}"' EXIT

mkdir -p "${FONT_DIR}"
log_info "Downloading ${URL}..."
curl -sSL "${URL}" -o "${TMP_DIR}/JetBrainsMono.tar.xz"

log_info "Extracting font files to ${FONT_DIR}..."
tar -xf "${TMP_DIR}/JetBrainsMono.tar.xz" -C "${FONT_DIR}"

if check_cmd fc-cache; then
    log_info "Refreshing font cache..."
    fc-cache -f "${FONT_DIR}"
fi

log_success "JetBrains Mono Nerd Font (${VERSION}) installed successfully."
