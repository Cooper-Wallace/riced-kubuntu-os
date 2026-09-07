# Reference System Specifications

This document captures the baseline configuration of the primary development machine. When testing scripts or replicating this environment, align with these baseline parameters.

## Operating System & Desktop
- **Distribution**: Ubuntu 26.04.1 LTS (Codename: Resolute)
- **Desktop Environment**: KDE Plasma 6.6.6
- **Windowing System**: Wayland
- **Default Shell**: `/bin/bash`
- **Linux Kernel**: `7.0.0-30-generic`

## Display & Graphics Profile
- **Session Type**: Wayland (`XDG_SESSION_TYPE=wayland`)
- **Display Scaling**: Check per-monitor scaling under System Settings > Display and Monitor.

## Development Tooling Priorities
- **Terminal**: Modern terminal emulator (e.g. Kitty / Konsole)
- **Editor / IDE**: Antigravity, VS Code, Neovim
- **Dotfile Management**: GNU Stow or symlink orchestrator in `scripts/03-dotfiles.sh`
- **Shell Customization**: Prompt enhancers (e.g. Starship / Fastfetch)
