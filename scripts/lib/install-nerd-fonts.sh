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
    log_success "JetBrains Mono Nerd Font is already installed."
    exit 0
fi

install_font() {
    local tmp_dir
    tmp_dir="$(mktemp -d)"
    curl -sSL "${URL}" -o "${tmp_dir}/JetBrainsMono.tar.xz"
    mkdir -p "${FONT_DIR}"
    tar -xf "${tmp_dir}/JetBrainsMono.tar.xz" -C "${FONT_DIR}"
    rm -rf "${tmp_dir}"
    if command -v fc-cache >/dev/null 2>&1; then
        fc-cache -f "${FONT_DIR}"
    fi
}
export -f install_font
export FONT_DIR URL

spin_task "Downloading and installing JetBrains Mono Nerd Font (${VERSION})" bash -c install_font
log_success "JetBrains Mono Nerd Font (${VERSION}) installed successfully."
