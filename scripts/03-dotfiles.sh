#!/usr/bin/env bash
# Stage 03: Symlink and Deploy Dotfiles
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
source "${SCRIPT_DIR}/lib/common.sh"

DRY_RUN=false
for arg in "$@"; do
    [[ "$arg" == "--dry-run" || "$arg" == "-n" ]] && DRY_RUN=true
done

log_info "Stage 03: Deploying dotfiles..."
DOTFILES_DIR="${REPO_ROOT}/dotfiles"

# 1. Deploy bash aliases / custom rc
if [[ -f "${DOTFILES_DIR}/bash/.bash_aliases" ]]; then
    log_info "Linking .bash_aliases -> ~/.bash_aliases"
    run_safe ln -sf "${DOTFILES_DIR}/bash/.bash_aliases" "${HOME}/.bash_aliases"
fi

# 2. Deploy .config subdirectories & files
if [[ -d "${DOTFILES_DIR}/config" ]]; then
    for item in "${DOTFILES_DIR}/config"/*; do
        [[ -e "$item" ]] || continue
        base="$(basename "$item")"
        target="${XDG_CONFIG_HOME:-$HOME/.config}/${base}"
        log_info "Linking config ${base} -> ${target}"
        run_safe mkdir -p "$(dirname "$target")"
        run_safe ln -snf "$item" "$target"
    done
fi

# 3. Deploy Konsole profiles and color schemes
KONSOLE_DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/konsole"
if [[ -d "${DOTFILES_DIR}/konsole" ]]; then
    log_info "Deploying Konsole profiles and color schemes..."
    run_safe mkdir -p "${KONSOLE_DATA_DIR}"
    for kfile in "${DOTFILES_DIR}/konsole"/*; do
        [[ -e "$kfile" ]] || continue
        kbase="$(basename "$kfile")"
        run_safe ln -sf "$kfile" "${KONSOLE_DATA_DIR}/${kbase}"
    done

    # Set RKO.profile as default Konsole profile
    if check_cmd kwriteconfig6; then
        log_info "Setting default Konsole profile to RKO.profile via kwriteconfig6..."
        run_safe kwriteconfig6 --file konsolerc --group "Desktop Entry" --key "DefaultProfile" "RKO.profile"
    fi
fi

# 4. Install JetBrains Mono Nerd Font
if [[ -f "${SCRIPT_DIR}/lib/install-nerd-fonts.sh" ]]; then
    log_info "Running JetBrains Mono Nerd Font installer..."
    bash "${SCRIPT_DIR}/lib/install-nerd-fonts.sh" "$@"
fi

log_success "Stage 03 complete."

