#!/usr/bin/env bash
# ==============================================================================
# backup-kde.sh - Export and sanitize portable KDE Plasma 6 configurations
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="${SCRIPT_DIR}/configs"
KDE_CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}"

mkdir -p "${TARGET_DIR}"

echo "==> Exporting KDE Plasma 6 configuration files..."

# Key configuration files to capture
FILES_TO_BACKUP=(
    "kdeglobals"
    "kwinrc"
    "kglobalshortcutsrc"
    "plasma-org.kde.plasma.desktop-appletsrc"
    "kcminputrc"
    "kfontinst"
    "breezerc"
    "plasmashellrc"
)

for file in "${FILES_TO_BACKUP[@]}"; do
    src="${KDE_CONFIG_DIR}/${file}"
    dst="${TARGET_DIR}/${file}"
    if [[ -f "${src}" ]]; then
        echo "  -> Copying ${file}..."
        cp "${src}" "${dst}"
    else
        echo "  -> Skipping ${file} (not found in ~/.config)"
    fi
done

echo "==> Sanitizing exported configs (removing hardware/session volatiles)..."

# Sanitize plasma applet IDs/session specific UUIDs if appletsrc exists
if [[ -f "${TARGET_DIR}/plasma-org.kde.plasma.desktop-appletsrc" ]]; then
    # Remove transient file dialog histories or recent documents
    sed -i '/^RecentFiles=/d' "${TARGET_DIR}/plasma-org.kde.plasma.desktop-appletsrc" 2>/dev/null || true
    # Replace absolute user home directory paths with portable $HOME placeholder
    sed -E -i 's|file:///home/[^/]+/|file://$HOME/|g' "${TARGET_DIR}/plasma-org.kde.plasma.desktop-appletsrc" 2>/dev/null || true
    sed -i 's|file://\$HOME/.*/dotfiles/wallpapers/|file://$HOME/.local/share/wallpapers/|g' "${TARGET_DIR}/plasma-org.kde.plasma.desktop-appletsrc" 2>/dev/null || true
fi

# Sanitize screen-specific resolutions or geometry from kwinrc if present
if [[ -f "${TARGET_DIR}/kwinrc" ]]; then
    # Strip monitor device serials/names to keep rules portable
    sed -i '/^Screen=/d' "${TARGET_DIR}/kwinrc" 2>/dev/null || true
fi

echo "==> KDE Plasma backup complete. Saved to: ${TARGET_DIR}"
echo "    Review changes with: git diff plasma/configs/"
