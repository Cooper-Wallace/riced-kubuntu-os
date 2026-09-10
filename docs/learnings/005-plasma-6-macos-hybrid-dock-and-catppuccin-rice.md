# 005 - KDE Plasma 6 macOS/Developer Hybrid Rice, Floating Dock, and Catppuccin Mocha Theme

- **Date**: 2026-09-10
- **Target Component**: Plasma 6 Shell / KWin / Wayland / Konsole / Theming
- **Environment**: Kubuntu 26.04 LTS (Plasma 6.6.6, Wayland)

---

### 1. Problem / Context
1. **Windows-Style Single Bottom Taskbar**: Default Kubuntu shipped with a single monolithic 54px bottom taskbar containing all widgets (Kickoff menu, workspace pager, taskbar, system tray, and clock). This felt outdated and lacked the clean visual separation of modern developer workstations.
2. **Terminal Transparency Noise**: Konsole had 5% background buffer transparency (`Opacity=0.95`). When positioned over white Chromium browser windows or documentation, background text bled through into the terminal buffer, creating severe visual noise and reducing code legibility.
3. **Muted Cyan/Blue Theming**: The default Breeze-Dark theme and Kubuntu desktop were saturated with harsh cyan blue (`#3daee9` / `61,174,233`) and muted slate blue (`30,87,116`), clashing with the Catppuccin Mocha terminal theme.
4. **Unstandardized Workspaces**: Virtual desktops defaulted to 2 desktops stacked in 2 rows (`Rows=2`), with default shortcuts colliding with Plasma's `activate task manager entry 3..4`.
5. **KDE Panel Floating & Dodge Configuration Drift**: Panel floating and window dodging properties in Plasma 6 are managed in `plasmashellrc` under `[PlasmaViews][Panel <id>]`, which was previously omitted from `FILES_TO_BACKUP` in `plasma/backup-kde.sh`.

---

### 2. Root Cause Analysis
- Konsole's background buffer transparency comes directly from `Opacity` in the active `.colorscheme` file; setting `Opacity=1` provides a 100% solid, opaque text buffer while KWin can maintain subtle window border blur.
- In KDE Plasma 6 under Wayland, floating panels and auto-hiding/dodge states (`panelVisibility=2`, `floating=1`, `panelLengthMode=1`) are written to `plasmashellrc` rather than `plasma-org.kde.plasma.desktop-appletsrc`.
- Task manager shortcut bindings `activate task manager entry 1..9` must be explicitly set to `none` in `kglobalshortcutsrc` to avoid intercepting `Meta+1..4` workspace switching.

---

### 3. Solution / Applied Fix

1. **Konsole Opacity**:
   - Updated `dotfiles/konsole/CatppuccinMocha.colorscheme` to `Opacity=1` (100% opaque solid background).
2. **Catppuccin Mocha Declarative Color Scheme**:
   - Created `dotfiles/color-schemes/RKO-CatppuccinMocha.colors` defining rich dark backgrounds (`30,30,46` / `24,24,37`) and soft Mauve (`203,166,247`) and Lavender (`180,190,254`) accents, replacing cyan blue.
   - Deployed to `~/.local/share/color-schemes/` in `scripts/03-dotfiles.sh` and applied via `plasma-apply-colorscheme`.
3. **macOS/Developer Hybrid Desktop Layout**:
   - Created `plasma/setup-layout.js` creating:
     - **Top Status & Workspace Bar**: 32px high, containing Kickoff launcher, workspace pager, centered clock, system tray, and desktop toggle.
     - **Bottom Centered Floating Dock**: 50px high, native Plasma 6 floating dock (`floating=1`, `panelVisibility=2` Window Dodge, `panelLengthMode=1` FitContent) with pinned developer tools (Konsole, VS Code, Chromium, Dolphin, Beekeeper, Bruno, Obsidian, Discord, System Settings).
4. **Virtual Desktop Standardisation**:
   - Set 3 standardized workspaces in `kwinrc`: `1: Web`, `2: Dev`, `3: Comms` with `Rows=1`.
   - Mapped `Meta+1..3` and `Meta+Shift+1..3` in `kglobalshortcutsrc` with task manager entries unbound.
   - Configured macOS-style traffic light window buttons (`ButtonsOnLeft=XIA`, `ButtonsOnRight=`) in `kwinrc` and `gtk-decoration-layout=close,minimize,maximize:` in GTK3/GTK4 settings.
5. **Curated Wallpapers & Backup Enhancements**:
   - Added resolution-independent minimalist wallpapers (`rko-catppuccin-peaks.jpg` and `rko-dark-topography.jpg`) in `dotfiles/wallpapers/`.
   - Updated `plasma/backup-kde.sh` to include `plasmashellrc` and normalize wallpaper paths to `$HOME/.local/share/wallpapers/`.

---

### 4. Replication Impact
- Running `./bootstrap.sh` on fresh Kubuntu machines automatically provisions the dual-panel hybrid layout, applies the Catppuccin Mocha color scheme and wallpaper, sets up 3 virtual desktops, and ensures solid terminal backgrounds with zero manual GUI configuration needed.
