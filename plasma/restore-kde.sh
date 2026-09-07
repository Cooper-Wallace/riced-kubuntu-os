#!/usr/bin/env bash
# ==============================================================================
# restore-kde.sh - Apply captured KDE Plasma 6 configurations
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="${SCRIPT_DIR}/configs"
KDE_CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}"
BACKUP_DIR="${KDE_CONFIG_DIR}/rko-plasma-backup-$(date +%Y%m%d%H%M%S)"

DRY_RUN=false
for arg in "$@"; do
    case "$arg" in
        --dry-run|-n) DRY_RUN=true ;;
    esac
done

if [[ ! -d "${SOURCE_DIR}" ]] || [[ -z "$(ls -A "${SOURCE_DIR}")" ]]; then
    echo "Error: No configurations found in ${SOURCE_DIR}."
    exit 1
fi

echo "==> Restoring KDE Plasma 6 configs..."
if [[ "${DRY_RUN}" == "true" ]]; then
    echo "  [DRY-RUN] Would backup current configs to: ${BACKUP_DIR}"
else
    mkdir -p "${BACKUP_DIR}"
fi

for config_file in "${SOURCE_DIR}"/*; do
    [[ -f "${config_file}" ]] || continue
    base_name="$(basename "${config_file}")"
    target_path="${KDE_CONFIG_DIR}/${base_name}"

    if [[ "${DRY_RUN}" == "true" ]]; then
        echo "  [DRY-RUN] Would copy ${base_name} -> ${target_path}"
    else
        if [[ -f "${target_path}" ]]; then
            cp "${target_path}" "${BACKUP_DIR}/"
        fi
        cp "${config_file}" "${target_path}"
        echo "  -> Restored ${base_name}"
    fi
done

echo ""
echo "==> Configuration restore complete."
if [[ "${DRY_RUN}" == "false" ]]; then
    echo "    To apply settings immediately, you may restart the shell or re-login:"
    echo "    kquitapp6 plasmashell && kstart plasmashell"
fi
