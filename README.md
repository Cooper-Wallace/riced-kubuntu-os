<p align="center">
  <img src="docs/assets/rko-banner.jpg" alt="Riced Kubuntu OS Banner" width="100%" />
</p>

# riced-kubuntu-os (RKO)

A reproducible, agentically maintainable configuration and automation suite for Kubuntu development environments.

Designed to:
1. **Replicate** your complete personalized Kubuntu OS setup (packages, dotfiles, KDE Plasma 6 rice) onto a fresh machine.
2. **Preserve Context & Learnings** across AI agent conversations with built-in Antigravity rules, skills, and atomic learning records.

---

## System Baseline

- **OS**: Kubuntu 26.04 LTS (Resolute)
- **Desktop**: KDE Plasma 6.6.6 (Wayland)
- **Kernel**: Linux 7.0+
- **Shell**: Bash

For detailed hardware and environment notes, see [docs/system-specs.md](docs/system-specs.md).

---

## Quickstart

### 1. Dry-Run Provisioning
Test the provisioning sequence without executing any changes on your system:
```bash
./bootstrap.sh --dry-run
```

### 2. Full System Provisioning
Execute all sequential provisioning stages:
```bash
./bootstrap.sh
```

Or execute a single stage (e.g. Stage `03` for dotfiles):
```bash
./bootstrap.sh --stage 03
```

---

## Capturing Your Current System State

To update this repository with customizations from your running machine:

1. **Capture KDE Plasma Configurations**:
   ```bash
   bash plasma/backup-kde.sh
   git diff plasma/configs/
   ```
2. **Audit & Update Package Manifests**:
   Compare installed packages with tracked manifests:
   ```bash
   # Check manual packages
   comm -13 <(sort -u manifests/apt-packages.list) <(apt-mark showmanual | sort -u)
   ```
3. **Record Learnings**:
   When fixing a machine-specific quirk, copy `docs/learnings/TEMPLATE.md` to a new entry in `docs/learnings/`.

---

## Repository Structure

```text
.
├── AGENTS.md                 # Agent routing instructions & principles
├── README.md                 # Human-facing guide
├── bootstrap.sh              # Master provisioner
├── .agents/                  # Agent skills & rules (Antigravity integration)
│   ├── rules/                # Bash safety and package hierarchy rules
│   └── skills/               # Snapshot & audit runbooks
├── docs/                     # System specifications, replication guide, learnings & ADRs
├── dotfiles/                 # Dotfiles ready for symlinking / GNU Stow
├── manifests/                # Declarative lists of APT, Flatpak, Snap & PPAs
├── plasma/                   # KDE Plasma 6 backup & restore scripts
├── scripts/                  # Sequential provisioning stages (00-05)
└── tests/                    # Automated & guarded-failure verification suites
```

---

## Waydroid Android Subsystem & Network Telemetry

Stage `05` (`scripts/05-waydroid.sh`) provisions a bloat-free Android 13 container on Wayland with:
- **ARM64 Support & Lightweight GMS**: `VANILLA` LineageOS image + `libhoudini` (Intel ARM translation) + `microG` + staged **Aurora Store** (`~/Waydroid/APKs/AuroraStore.apk`) and `persist.waydroid.fake_wifi=*` for running apps such as Instagram and Snapchat without full Google Play bloat.
- **Host ↔ Android Storage & Clipboard Bridge (`~/Waydroid`)**: Symlinks `Shared`, `Downloads`, `DCIM`, `Pictures`, `sdcard`, `APKs`, `logs`, and `captures` with POSIX default ACLs (`setfacl`) and `pyclip` + `wl-clipboard` clipboard sharing.
- **Chromium DevTools-Style Network Inspector & Telemetry (`waydroid-devtools`, `waydroid-stats` / `waydroid-netmon`, `waydroid-ctl`)**:
  - `waydroid-ctl start | stop | status | fix-perms | install-aurora | apps | shell | listen`
  - `waydroid-devtools` (or `waydroid-ctl listen`): Opens a browser Network Inspector on `http://127.0.0.1:8081` (`mitmdump` + `devtools_web_server.py` with trusted Android system CA) and automatically saves a local debugging copy of all requests (`requests.jsonl`), decoded API/JSON/WebSocket messages (`messages/*.json`, `websocket_messages.jsonl`), and loaded images/videos/media (`media/*`) in `~/Waydroid/captures/latest/`.
  - `waydroid-stats` (or `waydroid-netmon`): Live TUI + `--once`, `--json`, `--devtools`, `--log-telemetry <path>`, and `--pcap <path>` displaying `waydroid0` throughput, per-app Android sockets, live DNS/TLS SNI tracker categorization, DevTools requests, and recent Android downloads.
