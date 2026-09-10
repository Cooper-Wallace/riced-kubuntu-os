# 006 - Plasma 6 Pager Geometry, Lock Screen Avatar, and Dock Ergonomics

- **Date**: 2026-09-10
- **Target Component**: KDE Plasma 6 / KWin / VirtualDesktopManager / SDDM / Lock Screen
- **Environment**: Kubuntu 26.04 LTS (Plasma 6.6.6, Wayland)

---

### 1. Problem / Context
1. **Pager Label Truncation**: Standard KDE Plasma 6 pager (`org.kde.plasma.pager`) inside a compact 32px top panel truncated workspace names longer than 5 characters (e.g. `1: Web` became `1: W...` and `3: Comms` became `3: C...`).
2. **Virtual Desktop Persistence**: Modifying `kwinrc` on disk failed to create or rename virtual desktops dynamically in a running KWin session without a full logout or DBus intervention.
3. **Lock Screen Customization**: Default lock screen lacked visual continuity with the curated desktop wallpaper and showed a generic silhouette avatar instead of the user profile photo.
4. **Dock Launcher Organization & Icon Theme Drift**: Pinned dock items lacked ergonomic developer workflow ordering. Furthermore, third-party desktop apps (Beekeeper Studio, Bruno) used high-contrast default icons inconsistent with dark minimalist desktop aesthetics.

---

### 2. Root Cause Analysis
- **Pager Fixed Aspect Ratio**: `org.kde.plasma.pager` computes cell width strictly as `width = (panel_height / rows) * (16/9)`. In a 32px bar with 1 row, each cell is fixed at ~42.6px. There is no configuration key to widen pager cells independently. Long labels or numeric prefixes cause Qt's `Text.ElideRight` to clip text.
- **KWin Virtual Desktop Memory Model**: Virtual desktops are managed by an in-memory KWin service (`/VirtualDesktopManager`). KWin only syncs changes to `kwinrc` on clean exit; changes made to `kwinrc` while running are ignored until DBus calls signal desktop creation/renaming.
- **Lock Screen Asset Discovery**: `kscreenlocker_greet` looks specifically for `~/.face` (PNG format) and evaluates `~/.config/kscreenlockerrc` under `[Greeter][Wallpaper][org.kde.image][General]`.
- **Panel Translucency Architecture**: Native Plasma 6 panels use `panelOpacity=0` (Translucent) with KWin GPU-accelerated background blur to achieve macOS-style frosted glass aesthetics.

---

### 3. Solution / Applied Fix

1. **Untruncated Compact Pager Labels**:
   - Replaced verbose labels with compact 3-letter uppercase identifiers: `WEB`, `DEV`, `OPS`.
   - Render width at 10pt font is ~21px, fitting cleanly within the ~42.6px cell bounds with zero clipping in a single horizontal row.

2. **Automated Dynamic Virtual Desktop Management**:
   - Implemented dynamic creation and naming via DBus in `scripts/04-plasma-theming.sh`:
   ```bash
   ids=($(qdbus6 org.kde.KWin /VirtualDesktopManager org.kde.KWin.VirtualDesktopManager.desktops))
   qdbus6 org.kde.KWin /VirtualDesktopManager org.kde.KWin.VirtualDesktopManager.setDesktopName "${ids[0]}" "WEB"
   qdbus6 org.kde.KWin /VirtualDesktopManager org.kde.KWin.VirtualDesktopManager.setDesktopName "${ids[1]}" "DEV"
   qdbus6 org.kde.KWin /VirtualDesktopManager org.kde.KWin.VirtualDesktopManager.setDesktopName "${ids[2]}" "OPS"
   qdbus6 org.kde.KWin /VirtualDesktopManager org.freedesktop.DBus.Properties.Set org.kde.KWin.VirtualDesktopManager rows 1
   ```

3. **User Avatar & Lock Screen Declarative Sync**:
   - Converted user avatar to 512x512 PNG at `dotfiles/face/face.png`.
   - Deployed to `$HOME/.face` and `$HOME/.face.icon` in `scripts/03-dotfiles.sh`.
   - Exported `kscreenlockerrc` with wallpaper `rko-catppuccin-peaks.jpg` and added portable `$HOME` sanitization in `plasma/backup-kde.sh` and `plasma/restore-kde.sh`.

4. **Streamlined Dock Ordering & Backlog**:
   - Reorganized launcher array in `plasma/setup-layout.js` to:
     `System Settings -> Dolphin -> Konsole -> VS Code -> Obsidian -> Discord`.
   - **Backlog Item**: Beekeeper Studio and Bruno are omitted from the dock until color-theme compatible icons (Catppuccin / Monochrome SVG variants) are generated.

5. **Translucent Glass & Electric Cyan Accent**:
   - Configured `panelOpacity=0` for both top bar and floating dock.
   - Refined `RKO-CatppuccinMocha.colors` accent from Mauve (`#cba6f7`) to **Electric Sky / Antigravity Cyan** (`#38bdf8` / `56,189,248`).

---

### 4. Replication Impact
- Fully automated in `scripts/03-dotfiles.sh` (avatar deployment) and `scripts/04-plasma-theming.sh` (virtual desktops, wallpaper, and lock screen settings).
- Portable across any Kubuntu 26.04 machine via `./bootstrap.sh`.
