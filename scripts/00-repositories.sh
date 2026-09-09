#!/usr/bin/env bash
# Stage 00: Configure Package Repositories and PPAs
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
source "${SCRIPT_DIR}/lib/common.sh"

DRY_RUN=false
for arg in "$@"; do
    [[ "$arg" == "--dry-run" || "$arg" == "-n" ]] && DRY_RUN=true
done

log_info "Stage 00: Checking and applying software repositories..."
PPA_LIST="${REPO_ROOT}/manifests/ppas.list"

if [[ -f "${PPA_LIST}" ]]; then
    mapfile -t PPAS < <(grep -vE '^\s*(#|$)' "${PPA_LIST}" || true)
    for line in "${PPAS[@]}"; do
        if [[ "$line" =~ ^ppa: ]]; then
            spin_task "Configuring PPA repository: ${line}" sudo add-apt-repository -y "$line"
        fi
    done
fi

# Configure Microsoft VS Code repository
if ! check_cmd code && [[ ! -f /etc/apt/sources.list.d/vscode.list ]]; then
    setup_vscode_repo() {
        sudo install -D -m 644 /dev/null /etc/apt/keyrings/packages.microsoft.gpg
        curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | \
            gpg --dearmor | sudo tee /etc/apt/keyrings/packages.microsoft.gpg > /dev/null
        echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/packages.microsoft.gpg] https://packages.microsoft.com/repos/code stable main" | \
            sudo tee /etc/apt/sources.list.d/vscode.list > /dev/null
    }
    export -f setup_vscode_repo
    spin_task "Configuring Microsoft VS Code official APT repository" bash -c setup_vscode_repo
fi

spin_task "Updating APT package index" sudo apt-get update -y
log_success "Stage 00 complete."
