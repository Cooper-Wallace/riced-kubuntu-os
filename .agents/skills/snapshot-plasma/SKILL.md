---
name: snapshot-plasma
description: Use this skill when exporting, backing up, or synchronizing KDE Plasma 6 desktop configurations, shortcuts, panel widgets, and themes to the repository.
---

# Snapshot KDE Plasma State

This skill guides the agent through safely extracting the user's customized KDE Plasma 6 environment and committing portable configs to `plasma/configs/`.

## Procedure

1. **Review Changed Files in `~/.config`**:
   Examine key KDE configuration files:
   - `~/.config/kdeglobals` (Colors, icons, font settings)
   - `~/.config/kwinrc` (Window manager effects, virtual desktops, tiling)
   - `~/.config/kglobalshortcutsrc` (Keyboard shortcuts)
   - `~/.config/plasma-org.kde.plasma.desktop-appletsrc` (Panels, docks, and desktop widgets)
   - `~/.config/kcminputrc` (Mouse and touchpad curves)

2. **Execute the Sanitized Backup Script**:
   Run the repository's dedicated export tool:
   ```bash
   bash plasma/backup-kde.sh
   ```

3. **Verify Git Diff**:
   Inspect the changes in `plasma/configs/` using `git diff plasma/configs/`.
   - **Crucial**: Ensure no machine-specific screen resolutions, display UUIDs, recent file histories, or volatile window coordinates slipped through.

4. **Update `manifests/plasma-widgets.list`**:
   If custom plasmoids or KWin scripts were installed from the KDE Store, ensure their package or store names are documented in `manifests/plasma-widgets.list`.
