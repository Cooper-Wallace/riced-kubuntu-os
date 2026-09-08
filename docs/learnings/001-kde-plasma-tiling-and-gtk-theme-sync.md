# 001 - KDE Plasma 6 Desktop Usability, Tiling Shortcuts, and GTK Theme Sync

- **Date**: 2026-09-08
- **Target Component**: Plasma 6 / KWin / GTK Theming / Dotfile Symlinking
- **Environment**: Kubuntu 26.04 LTS (Plasma 6.6.6, Wayland)

---

### 1. Problem / Context
1. **Shortcut Conflicts**: Default KDE Plasma 6 binds `Meta+1` through `Meta+9` to `activate task manager entry 1..9`. This prevented ergonomic, tiling-window-manager-style direct workspace switching (`Meta+1` to `Browser + Productivity`, `Meta+2` to `Terminal + Development`), which defaulted awkwardly to `Meta+F1` / `Meta+F2`.
2. **Quarter-Screen Tiling**: Corner snapping (`Window Quick Tile Top Left / Top Right / Bottom Left / Bottom Right`) was unbound by default in Plasma 6.
3. **GTK Application White Flashes**: GTK 3 and GTK 4 applications under KDE Wayland defaulted to light themes (`gtk-application-prefer-dark-theme=false`), creating jarring visual contrast against the dark desktop and terminal rice.
4. **Dotfile Directory Symlink Recursion**: Running `ln -snf dotfiles/config/gtk-3.0 ~/.config/gtk-3.0` created a nested `~/.config/gtk-3.0/gtk-3.0` symlink because the target directory already existed on the host.

### 2. Root Cause Analysis
- `kglobalshortcutsrc` requires explicitly unbinding task manager entries (`none,none,...`) in the `[plasmashell]` group before `Meta+1` and `Meta+2` can be assigned to `Switch to Desktop 1` and `Switch to Desktop 2` in the `[kwin]` group.
- GTK applications require declarative `settings.ini` in `~/.config/gtk-3.0/` and `~/.config/gtk-4.0/` to enforce dark mode, Papirus Dark icons, and JetBrains Mono fonts.
- GNU `ln` when invoked with a directory target places the source directory *inside* the existing directory rather than merging or replacing individual files.

### 3. Solution / Applied Fix
1. Updated `plasma/configs/kglobalshortcutsrc`:
   - Set `activate task manager entry 1=none` and `entry 2=none`.
   - Bound `Switch to Desktop 1=Meta+1` and `Switch to Desktop 2=Meta+2`.
   - Bound `Window to Desktop 1=Meta+Shift+1` and `Window to Desktop 2=Meta+Shift+2`.
2. Quarter-tiling: Left as native KWin progressive corner snapping (`Meta+Left` followed by `Meta+Up`/`Meta+Down`), avoiding redundant custom bindings.
3. Created `dotfiles/config/gtk-3.0/settings.ini` and `dotfiles/config/gtk-4.0/settings.ini` enforcing `Breeze-Dark`, `Papirus-Dark`, and `JetBrainsMono Nerd Font`.
4. Updated `scripts/03-dotfiles.sh` to traverse subdirectories within `dotfiles/config/` and symlink individual configuration files idempotently.
5. Created `dotfiles/readline/.inputrc` for case-insensitive tab completion and Up/Down history prefix search.
6. Created `dotfiles/tmux/.tmux.conf` with modern `Ctrl-a` prefix and Catppuccin Mocha theme.
7. Populated `manifests/apt-packages.list` with `code` (VS Code) and KDE plugins, and `manifests/flatpaks.list` with Beekeeper Studio, Bruno, Obsidian, and Discord.

### 4. Replication Impact
- Executing `./bootstrap.sh` or running individual stages (`00` through `04`) cleanly applies these settings to any replicated Kubuntu machine.
- All configuration changes are captured in tracked dotfiles and sanitized in `plasma/configs/`.
