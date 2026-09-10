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
    spin_task "Restoring KDE Plasma 6 configurations and shortcuts" \
        bash "${REPO_ROOT}/plasma/restore-kde.sh" "${EXTRA_ARGS[@]}"
else
    log_warn "No saved Plasma configs found in plasma/configs/."
fi

# 2. Apply RKO Catppuccin Mocha color scheme
apply_colorscheme() {
    if [[ "${DRY_RUN}" == "true" ]]; then
        log_dry "plasma-apply-colorscheme RKO-CatppuccinMocha"
        return 0
    fi
    if command -v plasma-apply-colorscheme >/dev/null 2>&1; then
        plasma-apply-colorscheme "RKO-CatppuccinMocha" || true
    fi
}
export -f apply_colorscheme
export DRY_RUN
spin_task "Applying RKO Catppuccin Mocha color scheme" bash -c apply_colorscheme

# 3. Apply RKO desktop wallpaper
apply_wallpaper() {
    local wp_path="${XDG_DATA_HOME:-$HOME/.local/share}/wallpapers/rko-catppuccin-peaks.jpg"
    if [[ "${DRY_RUN}" == "true" ]]; then
        log_dry "Set wallpaper to ${wp_path}"
        return 0
    fi
    if [[ -f "${wp_path}" ]] && command -v qdbus6 >/dev/null 2>&1; then
        qdbus6 org.kde.plasmashell /PlasmaShell org.kde.PlasmaShell.evaluateScript "
            var ds = desktops();
            for (var i = 0; i < ds.length; i++) {
                ds[i].wallpaperPlugin = 'org.kde.image';
                ds[i].currentConfigGroup = ['Wallpaper', 'org.kde.image', 'General'];
                ds[i].writeConfig('Image', 'file://${wp_path}');
                ds[i].writeConfig('FillMode', 2);
            }
        " 2>/dev/null || true
    fi
    if command -v kwriteconfig6 >/dev/null 2>&1; then
        kwriteconfig6 --file kscreenlockerrc --group "Greeter" --group "Wallpaper" --group "org.kde.image" --group "General" --key "Image" "file://${wp_path}"
        kwriteconfig6 --file kscreenlockerrc --group "Greeter" --group "Wallpaper" --group "org.kde.image" --group "General" --key "PreviewImage" "file://${wp_path}"
        kwriteconfig6 --file kscreenlockerrc --group "Greeter" --group "Wallpaper" --group "org.kde.image" --group "General" --key "FillMode" 2
    fi
}
export -f apply_wallpaper
spin_task "Applying RKO Catppuccin Peaks desktop & lockscreen wallpaper" bash -c apply_wallpaper

# 4. Standardize virtual desktops (WEB, DEV, OPS in 1 horizontal row)
configure_virtual_desktops() {
    if [[ "${DRY_RUN}" == "true" ]]; then
        log_dry "Configure virtual desktops (WEB, DEV, OPS in 1 row via DBus)"
        return 0
    fi
    if command -v qdbus6 >/dev/null 2>&1; then
        local names=("WEB" "DEV" "OPS")
        local ids
        ids=($(qdbus6 org.kde.KWin /VirtualDesktopManager org.kde.KWin.VirtualDesktopManager.desktops 2>/dev/null || true))

        for i in 0 1 2; do
            if [[ $i -lt ${#ids[@]} ]]; then
                qdbus6 org.kde.KWin /VirtualDesktopManager org.kde.KWin.VirtualDesktopManager.setDesktopName "${ids[$i]}" "${names[$i]}" 2>/dev/null || true
            else
                qdbus6 org.kde.KWin /VirtualDesktopManager org.kde.KWin.VirtualDesktopManager.createDesktop "$i" "${names[$i]}" 2>/dev/null || true
            fi
        done

        ids=($(qdbus6 org.kde.KWin /VirtualDesktopManager org.kde.KWin.VirtualDesktopManager.desktops 2>/dev/null || true))
        if [[ ${#ids[@]} -gt 3 ]]; then
            for ((i=3; i<${#ids[@]}; i++)); do
                qdbus6 org.kde.KWin /VirtualDesktopManager org.kde.KWin.VirtualDesktopManager.removeDesktop "${ids[$i]}" 2>/dev/null || true
            done
        fi

        qdbus6 org.kde.KWin /VirtualDesktopManager org.freedesktop.DBus.Properties.Set org.kde.KWin.VirtualDesktopManager rows 1 2>/dev/null || true
    fi
}
export -f configure_virtual_desktops
spin_task "Standardizing virtual desktops (WEB, DEV, OPS in single row)" bash -c configure_virtual_desktops

# 5. Reload KWin window manager rules and global shortcuts
reload_kwin_services() {
    if [[ "${DRY_RUN}" == "true" ]]; then
        log_dry "qdbus6 org.kde.KWin /KWin reconfigure"
        log_dry "systemctl --user restart plasma-kglobalaccel.service"
        return 0
    fi
    if command -v qdbus6 >/dev/null 2>&1; then
        qdbus6 org.kde.KWin /KWin reconfigure 2>/dev/null || true
    fi
    if command -v systemctl >/dev/null 2>&1; then
        systemctl --user restart plasma-kglobalaccel.service 2>/dev/null || true
    fi
}
export -f reload_kwin_services
spin_task "Reloading KWin window manager effects and global shortcuts" bash -c reload_kwin_services

log_success "Stage 04 complete."
