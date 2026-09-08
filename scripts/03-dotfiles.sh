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

# 1. Deploy bash aliases, readline, and tmux configs to $HOME
deploy_home_configs() {
    [[ -f "${DOTFILES_DIR}/bash/.bash_aliases" ]] && ln -sf "${DOTFILES_DIR}/bash/.bash_aliases" "${HOME}/.bash_aliases"
    [[ -f "${DOTFILES_DIR}/readline/.inputrc" ]] && ln -sf "${DOTFILES_DIR}/readline/.inputrc" "${HOME}/.inputrc"
    [[ -f "${DOTFILES_DIR}/tmux/.tmux.conf" ]] && ln -sf "${DOTFILES_DIR}/tmux/.tmux.conf" "${HOME}/.tmux.conf"
}
export -f deploy_home_configs
export DOTFILES_DIR
spin_task "Deploying shell dotfiles (.bash_aliases, .inputrc, .tmux.conf)" bash -c deploy_home_configs

# 2. Deploy .config subdirectories & files
deploy_xdg_configs() {
    if [[ -d "${DOTFILES_DIR}/config" ]]; then
        for item in "${DOTFILES_DIR}/config"/*; do
            [[ -e "$item" ]] || continue
            base="$(basename "$item")"
            target="${XDG_CONFIG_HOME:-$HOME/.config}/${base}"
            if [[ -d "$item" ]]; then
                mkdir -p "$target"
                for subitem in "$item"/*; do
                    [[ -e "$subitem" ]] || continue
                    subbase="$(basename "$subitem")"
                    subtarget="${target}/${subbase}"
                    ln -sf "$subitem" "$subtarget"
                done
            else
                mkdir -p "$(dirname "$target")"
                ln -sf "$item" "$target"
            fi
        done
    fi
}
export -f deploy_xdg_configs
spin_task "Deploying XDG config files (Fastfetch, Fontconfig, GTK dark themes, Dolphin, KRunner)" bash -c deploy_xdg_configs

# 3. Deploy Konsole profiles and color schemes
deploy_konsole_configs() {
    local konsole_data_dir="${XDG_DATA_HOME:-$HOME/.local/share}/konsole"
    if [[ -d "${DOTFILES_DIR}/konsole" ]]; then
        mkdir -p "${konsole_data_dir}"
        for kfile in "${DOTFILES_DIR}/konsole"/*; do
            [[ -e "$kfile" ]] || continue
            ln -sf "$kfile" "${konsole_data_dir}/$(basename "$kfile")"
        done
        if command -v kwriteconfig6 >/dev/null 2>&1; then
            kwriteconfig6 --file konsolerc --group "Desktop Entry" --key "DefaultProfile" "RKO.profile"
        fi
    fi
}
export -f deploy_konsole_configs
spin_task "Configuring Konsole profile (RKO.profile) & Catppuccin Mocha theme" bash -c deploy_konsole_configs

# 4. Install JetBrains Mono Nerd Font
if [[ -f "${SCRIPT_DIR}/lib/install-nerd-fonts.sh" ]]; then
    extra_args=()
    [[ "${DRY_RUN}" == "true" ]] && extra_args+=("--dry-run")
    [[ "${VERBOSE}" == "true" ]] && extra_args+=("--verbose")
    bash "${SCRIPT_DIR}/lib/install-nerd-fonts.sh" "${extra_args[@]}"
fi

log_success "Stage 03 complete."

