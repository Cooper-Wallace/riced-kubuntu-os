# KOS (Riced Kubuntu OS) - Agent Directives & Architecture

Welcome to the **Riced-Kubuntu-OS (KOS)** repository. This repository stores code, declarative manifests, dotfiles, and system learnings to replicate this customized Kubuntu development environment onto any future machine.

## Repository Layout

```text
.
├── AGENTS.md                 # This file: Primary agent instructions and repository map
├── GEMINI.md                 # Symlink to AGENTS.md for compatibility
├── README.md                 # Human-oriented quickstart and bootstrap guide
├── bootstrap.sh              # Master orchestration script for provisioning fresh machines
│
├── .agents/                  # Antigravity agent customizations
│   ├── rules/                # Contextual guidelines (bash safety, packaging)
│   └── skills/               # Actionable runbooks (progressive disclosure)
│
├── docs/                     # Knowledge base
│   ├── system-specs.md       # Target machine hardware, OS, kernel, and desktop versions
│   ├── replication-guide.md  # Step-by-step human + automated installation checklist
│   ├── learnings/            # Atomic issue logs, quirks, and fixes
│   └── decisions/            # Architecture Decision Records (ADRs)
│
├── manifests/                # Declarative lists of installed packages and tools
├── dotfiles/                 # Tracked dotfiles (ready for GNU Stow or symlinking)
├── plasma/                   # KDE Plasma 6 configuration exporter and restorer
└── scripts/                  # Modular provisioning scripts executed by bootstrap.sh
```

## Guiding Principles for Agent Interactions

When working in this repository or interacting with the host system:

1. **Idempotence & Safety First**:
   - All scripts in [scripts/](file:///home/cooper/Projects/Riced-Kubuntu-OS/scripts/) and [plasma/](file:///home/cooper/Projects/Riced-Kubuntu-OS/plasma/) must be idempotent (safe to run multiple times without duplicating entries or causing data loss).
   - Scripts must support a `--dry-run` flag wherever destructive changes or package installations occur.
   - Never hardcode the absolute home directory path (`/home/cooper`). Always use `$HOME` or resolve dynamically.

2. **System Baseline Awareness**:
   - Inspect [docs/system-specs.md](file:///home/cooper/Projects/Riced-Kubuntu-OS/docs/system-specs.md) before assuming system utilities or display servers. The baseline environment is **Kubuntu 26.04 LTS**, **KDE Plasma 6**, and **Wayland**.

3. **Continuous Knowledge Maintenance (Learnings)**:
   - When solving a system bug, driver quirk, or custom configuration challenge, create a new record in [docs/learnings/](file:///home/cooper/Projects/Riced-Kubuntu-OS/docs/learnings/) using [docs/learnings/TEMPLATE.md](file:///home/cooper/Projects/Riced-Kubuntu-OS/docs/learnings/TEMPLATE.md).
   - If a recurring agent behavioral preference or workflow rule is established, suggest using `/learn` to persist it as a rule in [.agents/rules/](file:///home/cooper/Projects/Riced-Kubuntu-OS/.agents/rules/).

4. **KDE Plasma State Boundaries**:
   - Do NOT track entire raw directories from `~/.config/` blindly. KDE files frequently store volatile geometry, recent document histories, and hardware monitor IDs.
   - Use the sanitization procedures in [plasma/backup-kde.sh](file:///home/cooper/Projects/Riced-Kubuntu-OS/plasma/backup-kde.sh) and [.agents/skills/snapshot-plasma/SKILL.md](file:///home/cooper/Projects/Riced-Kubuntu-OS/.agents/skills/snapshot-plasma/SKILL.md).
