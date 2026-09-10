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
spin_task "Deploying user utility binaries (gdrive-stats, gdrive-import)" bash -c deploy_user_binaries

# 6. Deploy KDE Plasma color schemes and wallpapers
deploy_plasma_assets() {
    local schemes_src="${DOTFILES_DIR}/color-schemes"
    local schemes_dest="${XDG_DATA_HOME:-$HOME/.local/share}/color-schemes"
    if [[ -d "${schemes_src}" ]]; then
        mkdir -p "${schemes_dest}"
        for sfile in "${schemes_src}"/*; do
            [[ -e "$sfile" ]] || continue
            ln -sf "$sfile" "${schemes_dest}/$(basename "$sfile")"
        done
    fi

    local wallpapers_src="${DOTFILES_DIR}/wallpapers"
    local wallpapers_dest="${XDG_DATA_HOME:-$HOME/.local/share}/wallpapers"
    if [[ -d "${wallpapers_src}" ]]; then
        mkdir -p "${wallpapers_dest}"
        for wfile in "${wallpapers_src}"/*; do
            [[ -e "$wfile" ]] || continue
            ln -sf "$wfile" "${wallpapers_dest}/$(basename "$wfile")"
        done
    fi
}
export -f deploy_plasma_assets
spin_task "Deploying KDE Plasma color schemes and wallpapers" bash -c deploy_plasma_assets

# 7. Deploy user profile avatar (~/.face and ~/.face.icon)
deploy_user_avatar() {
    local avatar_url="https://raw.githubusercontent.com/Cooper-Wallace/Cooper-Wallace/main/assets/avatars/cooper_avatar.jpg"
    local local_avatar="${HOME}/Projects/Cooper-Wallace/assets/avatars/cooper_avatar.jpg"
    local face_dir="${DOTFILES_DIR}/face"
    local face_png="${face_dir}/face.png"
    local tmp_avatar="/tmp/rko-avatar-source.jpg"

    mkdir -p "${face_dir}"

    # Try fetching latest avatar from GitHub, fallback to local Cooper-Wallace repo if offline
    local source_img=""
    if command -v curl >/dev/null 2>&1; then
        if curl -fsSL --connect-timeout 5 --max-time 15 "${avatar_url}" -o "${tmp_avatar}" 2>/dev/null; then
            source_img="${tmp_avatar}"
        fi
    fi
    if [[ -z "${source_img}" && -f "${local_avatar}" ]]; then
        source_img="${local_avatar}"
    fi

    # If source obtained, resize & convert to 512x512 PNG at dotfiles/face/face.png
    if [[ -n "${source_img}" && -f "${source_img}" ]]; then
        python3 -c "
import sys
try:
    from PIL import Image
    im = Image.open('${source_img}')
    im = im.convert('RGBA')
    im = im.resize((512, 512), Image.Resampling.LANCZOS)
    im.save('${face_png}', 'PNG')
except Exception:
    sys.exit(0)
" 2>/dev/null || true
        rm -f "${tmp_avatar}"
    fi

    # Deploy to ~/.face and ~/.face.icon
    if [[ -f "${face_png}" ]]; then
        cp "${face_png}" "${HOME}/.face"
        ln -sf .face "${HOME}/.face.icon"
    fi
}
export -f deploy_user_avatar
spin_task "Deploying user avatar (~/.face and ~/.face.icon from Cooper-Wallace)" bash -c deploy_user_avatar

# 8. Install JetBrains Mono Nerd Font
if [[ -f "${SCRIPT_DIR}/lib/install-nerd-fonts.sh" ]]; then
    extra_args=()
    [[ "${DRY_RUN}" == "true" ]] && extra_args+=("--dry-run")
    [[ "${VERBOSE}" == "true" ]] && extra_args+=("--verbose")
    bash "${SCRIPT_DIR}/lib/install-nerd-fonts.sh" "${extra_args[@]}"
fi

log_success "Stage 03 complete."

