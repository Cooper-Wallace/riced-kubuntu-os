#!/usr/bin/env bash
# Stage 05: Provision Waydroid Android Subsystem, ARM Translation, Host Bridge & Telemetry
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
# shellcheck source=scripts/lib/common.sh disable=SC1091
source "${SCRIPT_DIR}/lib/common.sh"

DRY_RUN=false
VERBOSE=false
for arg in "$@"; do
    [[ "$arg" == "--dry-run" || "$arg" == "-n" ]] && DRY_RUN=true
    [[ "$arg" == "--verbose" || "$arg" == "-v" ]] && VERBOSE=true
done
export DRY_RUN VERBOSE REPO_ROOT

TARGET_USER="${USER:-$(id -un)}"
TARGET_HOME="${HOME}"
WAYDROID_DATA_DIR="${XDG_DATA_HOME:-${TARGET_HOME}/.local/share}/waydroid/data"
WAYDROID_SCRIPT_DIR="${XDG_DATA_HOME:-${TARGET_HOME}/.local/share}/waydroid-script"
export TARGET_USER TARGET_HOME WAYDROID_DATA_DIR WAYDROID_SCRIPT_DIR

log_info "Stage 05: Provisioning Waydroid Android Subsystem & Network Telemetry..."

# ------------------------------------------------------------------------------
# 1. Kernel Binder Module & Container Service Readiness
# ------------------------------------------------------------------------------
ensure_waydroid_service() {
    if ! lsmod | grep -q '^binder_linux'; then
        sudo modprobe binder_linux || true
    fi
    if [[ -d /etc/modules-load.d ]] && [[ ! -f /etc/modules-load.d/waydroid.conf ]]; then
        echo "binder_linux" | sudo tee /etc/modules-load.d/waydroid.conf > /dev/null
    fi
    if command -v systemctl >/dev/null 2>&1; then
        sudo systemctl enable --now waydroid-container.service || true
    fi
}
export -f ensure_waydroid_service
spin_task "Enabling kernel binder module and waydroid-container.service" bash -c ensure_waydroid_service

# ------------------------------------------------------------------------------
# 2. Initialize Waydroid VANILLA Image (De-bloated Android 13 / LineageOS)
# ------------------------------------------------------------------------------
init_waydroid_vanilla() {
    if [[ ! -f /var/lib/waydroid/images/system.img ]]; then
        sudo waydroid init -s VANILLA
    fi
}
export -f init_waydroid_vanilla
spin_task "Initializing Waydroid VANILLA Android system image" bash -c init_waydroid_vanilla

# ------------------------------------------------------------------------------
# 3. Install libhoudini (ARM64 Translation) & microG via casualsnek/waydroid_script
# ------------------------------------------------------------------------------
setup_waydroid_script_venv() {
    if [[ ! -d "${WAYDROID_SCRIPT_DIR}/.git" ]]; then
        mkdir -p "$(dirname "${WAYDROID_SCRIPT_DIR}")"
        git clone --depth 1 https://github.com/casualsnek/waydroid_script.git "${WAYDROID_SCRIPT_DIR}"
    else
        git -C "${WAYDROID_SCRIPT_DIR}" pull --ff-only || true
    fi
    if [[ ! -x "${WAYDROID_SCRIPT_DIR}/.venv/bin/python3" ]]; then
        python3 -m venv "${WAYDROID_SCRIPT_DIR}/.venv"
    fi
    "${WAYDROID_SCRIPT_DIR}/.venv/bin/pip" install --quiet --upgrade pip
    "${WAYDROID_SCRIPT_DIR}/.venv/bin/pip" install --quiet -r "${WAYDROID_SCRIPT_DIR}/requirements.txt"
}
export -f setup_waydroid_script_venv
spin_task "Preparing waydroid_script Python environment" bash -c setup_waydroid_script_venv

install_waydroid_clipboard_pyclip() {
    if [[ -d /usr/lib/waydroid ]] && ! PYTHONPATH=/usr/lib/waydroid python3 -c "import pyclip" >/dev/null 2>&1; then
        sudo "${WAYDROID_SCRIPT_DIR}/.venv/bin/pip" install --quiet --upgrade --target /usr/lib/waydroid pyclip
    fi
}
export -f install_waydroid_clipboard_pyclip
spin_task "Ensuring Waydroid Wayland clipboard bridge (pyclip)" bash -c install_waydroid_clipboard_pyclip

install_libhoudini_and_microg() {
    local need_houdini=false
    local need_microg=false

    if [[ ! -f /var/lib/waydroid/overlay/system/etc/init/houdini.rc && ! -f /var/lib/waydroid/overlay/system/bin/houdini64 ]] \
       && ! grep -q "libhoudini.so" /var/lib/waydroid/waydroid_base.prop 2>/dev/null; then
        need_houdini=true
    fi

    if [[ ! -f /var/lib/waydroid/overlay/system/bin/npem \
       && ! -d /var/lib/waydroid/overlay/system/priv-app/GmsCore \
       && ! -d /var/lib/waydroid/overlay/system/priv-app/PrebuiltGmsCore ]]; then
        need_microg=true
    fi

    local targets=()
    [[ "${need_houdini}" == "true" ]] && targets+=("libhoudini")
    [[ "${need_microg}" == "true" ]] && targets+=("microg")

    if [[ ${#targets[@]} -gt 0 ]]; then
        (
            cd "${WAYDROID_SCRIPT_DIR}"
            sudo "${WAYDROID_SCRIPT_DIR}/.venv/bin/python3" "${WAYDROID_SCRIPT_DIR}/main.py" -a 13 install "${targets[@]}"
        )
    fi
}
export -f install_libhoudini_and_microg
spin_task "Installing libhoudini (ARM translation) and microG (lightweight GMS)" bash -c install_libhoudini_and_microg

install_mitm_ca_cert() {
    local mitm_dir="${TARGET_HOME}/.mitmproxy"
    local ca_cert="${mitm_dir}/mitmproxy-ca-cert.pem"

    if [[ ! -f "${ca_cert}" ]] && command -v mitmdump >/dev/null 2>&1; then
        mkdir -p "${mitm_dir}"
        timeout 3 mitmdump -n -q --listen-port 18089 >/dev/null 2>&1 || true
    fi

    if [[ -f "${ca_cert}" ]] && command -v openssl >/dev/null 2>&1; then
        local cert_hash
        cert_hash="$(openssl x509 -noout -subject_hash_old -in "${ca_cert}")"
        local cacert_dest="/var/lib/waydroid/overlay/system/etc/security/cacerts/${cert_hash}.0"
        if [[ ! -f "${cacert_dest}" ]]; then
            (
                cd "${WAYDROID_SCRIPT_DIR}"
                sudo "${WAYDROID_SCRIPT_DIR}/.venv/bin/python3" "${WAYDROID_SCRIPT_DIR}/main.py" -a 13 install mitm -c "${ca_cert}"
            )
            if [[ ! -f "${cacert_dest}" ]]; then
                sudo install -d -m 755 "$(dirname "${cacert_dest}")"
                sudo install -m 644 "${ca_cert}" "${cacert_dest}"
            fi
        fi
    fi
}
export -f install_mitm_ca_cert
spin_task "Generating and trusting mitmproxy Root CA in Android system store" bash -c install_mitm_ca_cert

# ------------------------------------------------------------------------------
# 4. Configure Waydroid Properties & UFW Bridge Networking
# ------------------------------------------------------------------------------
configure_waydroid_properties_and_net() {
    if [[ -f /var/lib/waydroid/waydroid.cfg ]]; then
        sudo python3 - <<'PYEOF'
import configparser
from pathlib import Path

cfg_path = Path("/var/lib/waydroid/waydroid.cfg")
cfg = configparser.ConfigParser()
cfg.optionxform = str
cfg.read(cfg_path)
if "properties" not in cfg:
    cfg["properties"] = {}

desired = {
    "persist.waydroid.multi_windows": "true",
    "persist.waydroid.fake_wifi": "*",
    "persist.waydroid.uevent": "true",
    "debug.stagefright.ccodec": "4",
}
changed = False
for k, v in desired.items():
    if cfg["properties"].get(k) != v:
        cfg["properties"][k] = v
        changed = True

if changed:
    with cfg_path.open("w", encoding="utf-8") as fh:
        cfg.write(fh)
PYEOF
    fi

    if command -v waydroid >/dev/null 2>&1; then
        if waydroid status 2>/dev/null | grep -qE "Session:\s+RUNNING"; then
            waydroid prop set persist.waydroid.multi_windows true || true
            waydroid prop set persist.waydroid.fake_wifi '*' || true
            waydroid prop set persist.waydroid.uevent true || true
        fi
    fi

    if command -v ufw >/dev/null 2>&1; then
        if sudo ufw status 2>/dev/null | grep -q "Status: active"; then
            sudo ufw allow in on waydroid0 to any port 53 proto udp comment "Waydroid DNS UDP" || true
            sudo ufw allow in on waydroid0 to any port 53 proto tcp comment "Waydroid DNS TCP" || true
            sudo ufw allow in on waydroid0 to any port 67 proto udp comment "Waydroid DHCP" || true
            sudo ufw route allow in on waydroid0 comment "Waydroid bridge inbound route" || true
            sudo ufw route allow out on waydroid0 comment "Waydroid bridge outbound route" || true
        fi
    fi
}
export -f configure_waydroid_properties_and_net
spin_task "Configuring Waydroid properties (multi_windows, fake_wifi, uevent) & firewall rules" bash -c configure_waydroid_properties_and_net

# ------------------------------------------------------------------------------
# 5. Host <-> Android Filesystem Bridge (~/Waydroid), ACLs & Aurora Store APK
# ------------------------------------------------------------------------------
setup_waydroid_host_bridge() {
    local bridge_root="${TARGET_HOME}/Waydroid"
    local media_zero="${WAYDROID_DATA_DIR}/media/0"

    mkdir -p "${bridge_root}/APKs" "${bridge_root}/logs" "${bridge_root}/captures"

    # Create LinuxShared only if Android media/0 already initialized, else link cleanly
    if [[ -d "${media_zero}" ]]; then
        sudo mkdir -p "${media_zero}/LinuxShared" "${media_zero}/Download" "${media_zero}/DCIM" "${media_zero}/Pictures"
        if command -v setfacl >/dev/null 2>&1; then
            sudo setfacl -R -m "u:${TARGET_USER}:rwx" "${WAYDROID_DATA_DIR}/media" || true
            sudo setfacl -R -d -m "u:${TARGET_USER}:rwx" "${WAYDROID_DATA_DIR}/media" || true
        fi
    fi

    # Symlink key Android directories into ~/Waydroid
    ln -sfn "${media_zero}/LinuxShared" "${bridge_root}/Shared"
    ln -sfn "${media_zero}/Download" "${bridge_root}/Downloads"
    ln -sfn "${media_zero}/DCIM" "${bridge_root}/DCIM"
    ln -sfn "${media_zero}/Pictures" "${bridge_root}/Pictures"
    ln -sfn "${media_zero}" "${bridge_root}/sdcard"

    # Stage Aurora Store APK for bloat-free Instagram/Snapchat installation
    local aurora_apk="${bridge_root}/APKs/AuroraStore.apk"
    if [[ ! -s "${aurora_apk}" ]]; then
        local ver_code="76"
        local api_json=""
        if api_json="$(curl -fsSL --connect-timeout 5 --max-time 15 "https://f-droid.org/api/v1/packages/com.aurora.store" 2>/dev/null || true)"; then
            local parsed
            parsed="$(printf '%s' "${api_json}" | jq -r '.suggestedVersionCode // empty' 2>/dev/null || true)"
            [[ -n "${parsed}" ]] && ver_code="${parsed}"
        fi
        local tmp_apk="/tmp/AuroraStore-${ver_code}.apk"
        if curl -fsSL --connect-timeout 10 --max-time 120 "https://f-droid.org/repo/com.aurora.store_${ver_code}.apk" -o "${tmp_apk}"; then
            mv -f "${tmp_apk}" "${aurora_apk}"
        else
            rm -f "${tmp_apk}"
            log_warn "Could not download Aurora Store APK (offline or unreachable); retry later with waydroid-ctl install-aurora."
        fi
    fi
}
export -f setup_waydroid_host_bridge
spin_task "Setting up ~/Waydroid host bridge, POSIX ACLs, and Aurora Store APK" bash -c setup_waydroid_host_bridge

# ------------------------------------------------------------------------------
# 6. Non-Interactive Network Telemetry Sudoers Policy
# ------------------------------------------------------------------------------
setup_telemetry_sudoers() {
    local sudoers_dest="/etc/sudoers.d/rko-waydroid-telemetry"
    local tmp_sudoers
    tmp_sudoers="$(mktemp)"

    local cmds=()
    local bin_name bin_path
    for bin_name in nsenter ss tcpdump tshark setfacl waydroid lxc-info iptables iptables-legacy; do
        bin_path="$(command -v "${bin_name}" 2>/dev/null || true)"
        if [[ -n "${bin_path}" ]]; then
            cmds+=("${bin_path}")
        fi
    done

    if [[ ${#cmds[@]} -eq 0 ]]; then
        rm -f "${tmp_sudoers}"
        return 0
    fi

    local joined_cmds
    joined_cmds="$(IFS=', '; echo "${cmds[*]}")"

    {
        echo "# Managed by riced-kubuntu-os (scripts/05-waydroid.sh)"
        echo "# Allows non-interactive network telemetry inspection and Waydroid ACL management"
        echo "${TARGET_USER} ALL=(root) NOPASSWD: ${joined_cmds}"
    } > "${tmp_sudoers}"

    if sudo visudo -cf "${tmp_sudoers}" >/dev/null 2>&1; then
        sudo install -m 0440 -o root -g root "${tmp_sudoers}" "${sudoers_dest}"
    else
        rm -f "${tmp_sudoers}"
        log_error "Generated sudoers policy failed visudo validation!"
        return 1
    fi
    rm -f "${tmp_sudoers}"
}
export -f setup_telemetry_sudoers
spin_task "Configuring passwordless sudoers policy for waydroid-stats telemetry" bash -c setup_telemetry_sudoers

log_success "Stage 05 complete. Launch Waydroid via 'waydroid-ctl start' and monitor traffic with 'waydroid-stats'."
