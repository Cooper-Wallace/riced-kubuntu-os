#!/usr/bin/env bash
# Stage 03: Symlink and Deploy Dotfiles
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
source "${SCRIPT_DIR}/lib/common.sh"

DRY_RUN=false
VERBOSE=false
for arg in "$@"; do
    [[ "$arg" == "--dry-run" || "$arg" == "-n" ]] && DRY_RUN=true
    [[ "$arg" == "--verbose" || "$arg" == "-v" ]] && VERBOSE=true
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
            [[ "$base" == "systemd" ]] && continue
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

# 3. Deploy systemd user services (e.g. Google Drive auto-mount)
deploy_systemd_user_services() {
    local systemd_src="${DOTFILES_DIR}/config/systemd/user"
    local systemd_dest="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
    if [[ -d "${systemd_src}" ]]; then
        mkdir -p "${systemd_dest}"
        for sfile in "${systemd_src}"/*; do
            [[ -e "$sfile" ]] || continue
            [[ -f "$sfile" ]] || continue
            ln -sf "$sfile" "${systemd_dest}/$(basename "$sfile")"
        done
        if command -v systemctl >/dev/null 2>&1; then
            systemctl --user daemon-reload || true
            systemctl --user enable rclone-gdrive.service || true
            if [[ -f "${HOME}/.config/rclone/rclone.conf" ]]; then
                systemctl --user start rclone-gdrive.service || true
            fi
        fi
    fi
}
export -f deploy_systemd_user_services
spin_task "Deploying systemd user services (Rclone Google Drive mount)" bash -c deploy_systemd_user_services

# 4. Deploy Konsole profiles and color schemes
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

# 5. Deploy user utility binaries (~/.local/bin)
deploy_user_binaries() {
    local bin_src="${DOTFILES_DIR}/bin"
    local bin_dest="${HOME}/.local/bin"
    if [[ -d "${bin_src}" ]]; then
        mkdir -p "${bin_dest}"
        for bfile in "${bin_src}"/*; do
            [[ -e "$bfile" ]] || continue
            [[ -f "$bfile" ]] || continue
            chmod +x "$bfile"
            ln -sf "$bfile" "${bin_dest}/$(basename "$bfile")"
        done
    fi
}
export -f deploy_user_binaries
spin_task "Deploying user utility binaries (~/.local/bin/gdrive-stats)" bash -c deploy_user_binaries

# 6. Install JetBrains Mono Nerd Font
if [[ -f "${SCRIPT_DIR}/lib/install-nerd-fonts.sh" ]]; then
    extra_args=()
    [[ "${DRY_RUN}" == "true" ]] && extra_args+=("--dry-run")
    [[ "${VERBOSE}" == "true" ]] && extra_args+=("--verbose")
    bash "${SCRIPT_DIR}/lib/install-nerd-fonts.sh" "${extra_args[@]}"
fi

log_success "Stage 03 complete."

