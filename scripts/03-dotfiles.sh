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

# 2. Deploy .config subdirectories
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

log_success "Stage 03 complete."
