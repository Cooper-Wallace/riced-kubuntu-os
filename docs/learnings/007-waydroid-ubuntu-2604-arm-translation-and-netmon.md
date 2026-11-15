# 007 - Waydroid on Kubuntu 26.04 LTS: ARM Translation, Host Sharing & Network Telemetry

- **Date**: 2026-11-15
- **Target Component**: Waydroid / LXC / Wayland / ARM Translation / Network Telemetry
- **Environment**: Kubuntu 26.04 LTS (`resolute`, Kernel `7.0.0-38-generic`, KDE Plasma 6.6.6 Wayland, Intel Iris Xe `x86_64`)

---

### 1. Problem / Context
Running Android social media apps (such as Instagram and Snapchat) on Kubuntu 26.04 LTS Wayland presented several technical requirements:
1. **Upstream Repository & Dependency Gaps**: `waydroid` is not shipped in Ubuntu's default `resolute` APT mirrors, and Ubuntu 26.04 lacks `python3-pyclip` (which Waydroid's clipboard manager uses for Wayland clipboard sync) as well as `ensurepip` unless `python3-venv` is explicitly installed.
2. **Bloat-Free App Compatibility on Intel `x86_64`**: Social media apps ship ARM64 native binaries and often require Wi-Fi state detection plus Google Cloud Messaging / Firebase push notifications, yet full Google Play Services (`GAPPS`) introduces unwanted background bloat.
3. **Host ↔ Android File Sharing Friction**: Waydroid isolates `/data/media/0` under Android UID `1023` (`media_rw`), creating Linux host read/write permission friction when accessing Android downloads, photos, and shared files.
4. **Network Telemetry & Traffic Visibility**: Users and agents need real-time visibility from the Linux host into per-app Android sockets, live DNS/TLS SNI telemetry domains, bandwidth consumption, and downloaded files.

### 2. Root Cause Analysis
1. **APT Repository Structure**: `https://repo.waydro.id/dists/resolute/Release` serves `main/binary-all/Packages.gz`, requiring `[signed-by=/etc/apt/keyrings/waydroid.gpg]` without `[arch=amd64]` scoping.
2. **ARM64 Execution & Lightweight GMS**: On Intel TigerLake `x86_64` hosts, `libhoudini` registers ARM32/ARM64 `binfmt_misc` handlers inside the Android container, while `microG` provides lightweight GCM/Firebase compatibility without full Play Store services. Additionally, setting `persist.waydroid.fake_wifi=*` prevents apps from rejecting Waydroid's virtual `eth0` bridge as offline.
3. **Storage Ownership**: Android's `media_rw` (`1023`) ownership on `~/.local/share/waydroid/data/media/0` blocks normal Linux user writes unless default POSIX ACLs (`setfacl -R -m u:$USER:rwx` and `setfacl -R -d -m u:$USER:rwx`) are applied.
4. **Container Network Namespace & Ubuntu 26.04 `mitmweb` Packaging Bug**: Android runs inside an isolated LXC network namespace bridged to `waydroid0` on the host, so inspecting `/sys/class/net/waydroid0/statistics/`, running `nsenter` + `ss` (or `/proc/<lxc_pid>/net/{tcp,udp}*`) mapped against `data/system/packages.list` UIDs, and passively sniffing DNS/TLS SNI on `waydroid0` provides per-app telemetry. For full Chromium DevTools-style HTTP/HTTPS/WebSocket inspection, Ubuntu 26.04's `mitmproxy==8.1.1-4` APT package suffers from an import-time `NameError: name 'State' is not defined` bug in `/usr/lib/python3/dist-packages/mitmproxy/tools/web/app.py`, breaking `/usr/bin/mitmweb` while `/usr/bin/mitmdump` works cleanly. Pairing `mitmdump` + a local Python `devtools_capture_addon.py` + zero-dependency `devtools_web_server.py` solves this cleanly.

### 3. Solution / Applied Fix
1. **Official Waydroid Repository (`scripts/00-repositories.sh` & `manifests/ppas.list`)**:
   - Probed `resolute`, `noble`, and `sid` on `https://repo.waydro.id/`, installed `/etc/apt/keyrings/waydroid.gpg`, and configured `/etc/apt/sources.list.d/waydroid.list`.
2. **Declarative Package Manifest (`manifests/apt-packages.list`)**:
   - Added `waydroid`, `lxc`, `wl-clipboard`, `python3-pyperclip`, `python3-venv`, `lzip`, `sqlite3`, `adb`, `acl`, `tcpdump`, `tshark`, `mitmproxy`, and `openssl`.
3. **Automated Stage 05 Provisioner (`scripts/05-waydroid.sh`)**:
   - Loaded `binder_linux` (`/etc/modules-load.d/waydroid.conf`) and enabled `waydroid-container.service`.
   - Initialized the de-bloated `VANILLA` LineageOS image (`sudo waydroid init -s VANILLA`).
   - Provisioned `casualsnek/waydroid_script` in `~/.local/share/waydroid-script/.venv`, installed `pyclip` into `/usr/lib/waydroid` for Wayland clipboard sharing, and installed `libhoudini` + `microg` for Android 13.
   - Generated `~/.mitmproxy/mitmproxy-ca-cert.pem` and installed it into Android's system trust store (`/var/lib/waydroid/overlay/system/etc/security/cacerts/<hash>.0`) via `waydroid_script install mitm` so HTTPS traffic can be inspected without app-level warnings on non-pinned endpoints.
   - Configured `/var/lib/waydroid/waydroid.cfg` (`persist.waydroid.multi_windows=true`, `persist.waydroid.fake_wifi=*`, `persist.waydroid.uevent=true`) and UFW bridge rules if active.
   - Bridged Android storage into `~/Waydroid/{Shared,Downloads,DCIM,Pictures,sdcard,APKs,logs,captures}`, applied recursive + default POSIX ACLs, and staged the latest Aurora Store APK (`com.aurora.store`).
   - Installed `/etc/sudoers.d/rko-waydroid-telemetry` (validated via `visudo -cf`) for passwordless read-only telemetry inspection and transparent `iptables` redirection on `waydroid0`.
4. **Chromium DevTools-Style Network Inspector & Local Persistence (`waydroid-devtools`, `devtools_capture_addon.py`, `devtools_web_server.py`, `waydroid-stats`)**:
   - `waydroid-devtools` attaches transparent `waydroid0` port `80`/`443` `iptables` redirection (with automatic cleanup trap on exit) and launches `mitmdump` with `devtools_capture_addon.py` alongside the zero-dependency Chromium DevTools-style Web UI (`devtools_web_server.py` at `http://127.0.0.1:8081`).
   - Every active session automatically persists local debugging copies in `~/Waydroid/captures/latest/`: `requests.jsonl` (categorized into `Fetch/XHR`, `Img`, `Media`, `WS`, `Doc`, etc.), `messages/*.json` (decoded API/JSON/GraphQL/text payloads), `media/*` (loaded images, videos, audio, and binaries), and `websocket_messages.jsonl`.
   - Built `waydroid-stats` (`waydroid-netmon`) `rich` live TUI integrating `waydroid0` throughput, per-app Android sockets, live DNS/TLS SNI feeds, recent `~/Waydroid` downloads, and the live DevTools request/capture stream (`--devtools` / key `l`).
   - Built `waydroid-ctl` for deterministic lifecycle management (`start`, `stop`, `status`, `fix-perms`, `install-aurora`, `install-apk`, `apps`, `shell`, `listen`, `init-gapps`).

```bash
# Provision Waydroid stage and verify status/telemetry
./bootstrap.sh --stage 05
waydroid-ctl start
waydroid-ctl install-aurora
waydroid-devtools                 # Opens DevTools Network UI on http://127.0.0.1:8081 + saves to ~/Waydroid/captures/latest
waydroid-stats --devtools         # Live TUI with embedded DevTools capture listener
```

### 4. Replication Impact
- Registered Stage `05` (`scripts/05-waydroid.sh`) in `bootstrap.sh` and updated Stage `00`, `01`, and `03` manifests and binary deployment.
- Fresh Kubuntu machines running `./bootstrap.sh` automatically configure Waydroid, `libhoudini`, `microG`, `~/Waydroid` POSIX ACLs, `waydroid-ctl`, and `waydroid-stats` (`waydroid-netmon`).
- Automated regression and guarded-failure checks live in `tests/test_waydroid.sh`.
