#!/usr/bin/env bash
# ==============================================================================
# bootstrap.sh - Master Orchestrator for riced-kubuntu-os (RKO)
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/scripts/lib/common.sh"

DRY_RUN=false
TARGET_STAGE=""

print_usage() {
    echo -e "${BOLD}Usage:${NC} ./bootstrap.sh [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -n, --dry-run        Simulate execution without modifying the host"
    echo "  -s, --stage <00-04>  Run only a specific stage (e.g. 01, 03)"
    echo "  -h, --help           Show this help message"
    echo ""
    echo "Available Stages:"
    echo "  00 : Configure repositories & PPAs (scripts/00-repositories.sh)"
    echo "  01 : Install base APT packages (scripts/01-apt-core.sh)"
    echo "  02 : Install Flatpaks & Snaps (scripts/02-snaps-flatpaks.sh)"
    echo "  03 : Deploy dotfiles (scripts/03-dotfiles.sh)"
    echo "  04 : Apply KDE Plasma 6 configurations (scripts/04-plasma-theming.sh)"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        -n|--dry-run)
            DRY_RUN=true
            shift
            ;;
        -s|--stage)
            TARGET_STAGE="$2"
            shift 2
            ;;
        -h|--help)
            print_usage
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            print_usage
            exit 1
            ;;
    esac
done

export DRY_RUN

echo -e "${BOLD}${BLUE}=====================================================${NC}"
echo -e "${BOLD}${BLUE}   riced-kubuntu-os (RKO) Bootstrap Provisioner      ${NC}"
echo -e "${BOLD}${BLUE}=====================================================${NC}"

if [[ "${DRY_RUN}" == "true" ]]; then
    log_warn "Running in DRY-RUN mode. No system changes will be made."
fi

STAGES=(
    "00:${SCRIPT_DIR}/scripts/00-repositories.sh"
    "01:${SCRIPT_DIR}/scripts/01-apt-core.sh"
    "02:${SCRIPT_DIR}/scripts/02-snaps-flatpaks.sh"
    "03:${SCRIPT_DIR}/scripts/03-dotfiles.sh"
    "04:${SCRIPT_DIR}/scripts/04-plasma-theming.sh"
)

for item in "${STAGES[@]}"; do
    stage_id="${item%%:*}"
    script_path="${item##*:}"

    if [[ -n "${TARGET_STAGE}" && "${TARGET_STAGE}" != "${stage_id}" ]]; then
        continue
    fi

    echo ""
    log_info "Executing Stage [${stage_id}]: $(basename "${script_path}")..."
    if [[ "${DRY_RUN}" == "true" ]]; then
        bash "${script_path}" --dry-run
    else
        bash "${script_path}"
    fi
done

echo ""
log_success "RKO Bootstrap execution finished!"
if [[ "${DRY_RUN}" == "false" ]]; then
    echo -e "Remember to restart your KDE Plasma session or log out/in to apply all desktop changes."
fi
