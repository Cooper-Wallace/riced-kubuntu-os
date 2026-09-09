# riced-kubuntu-os (RKO)

<p align="center">
  <img src="docs/assets/rko-logo.jpg" alt="Riced Kubuntu OS Logo" width="200" />
</p>

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
└── scripts/                  # Sequential provisioning stages (00-04)
```
