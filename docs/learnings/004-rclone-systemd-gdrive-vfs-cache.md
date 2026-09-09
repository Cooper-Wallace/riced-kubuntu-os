# 004 - Rclone Google Drive Systemd User Service & VFS Cache Management

- **Date**: 2026-09-09
- **Target Component**: Systemd User Services / Rclone / Cloud Storage / FUSE
- **Environment**: Kubuntu 26.04 LTS (KDE Plasma 6.x, Wayland)

---

### 1. Problem / Context
When configuring Google Drive as a persistent mapped drive using `rclone mount` under a `systemd` user service (`rclone-gdrive.service`), several issues arose:
1. File operations and `findmnt` queries appeared to hang indefinitely.
2. The service entered failure or restart loops when `--log-file` directories were missing or when cache verification hit Google Drive API rate limits (`RATE_LIMIT_EXCEEDED` 403).
3. Linking `~/.config/systemd/user` directly via dotfile symlinkers caused `systemctl --user enable` to write runtime `default.target.wants` symlinks inside the Git repository working tree.

### 2. Root Cause Analysis
1. **Unclean VFS Cache Recovery**: When `rclone mount` with `--vfs-cache-mode full` is terminated while files are actively cached (for instance, when Dolphin's thumbnail generator reads large media directories), rclone treats those cache files as pending uploads upon next startup. If hundreds of files exist in the cache, rclone attempts synchronous hash verification and queuing before the FUSE mount is presented. This triggers Google Drive's per-minute API rate limiter, forcing exponential backoff (e.g. 4.5s per request) and stalling filesystem availability.
2. **Missing Pre-requisite Directories**: `rclone` does not create parent directories for its `--log-file` flag. If `~/.cache/rclone` does not exist, `rclone mount` exits immediately with status code 1.
3. **Dotfile Symlink Folding**: If `~/.config/systemd/user` is symlinked as an entire folder to `dotfiles/config/systemd/user`, running `systemctl --user enable <service>` places `.wants` symlinks directly inside the Git repository, polluting `git status`.

### 3. Solution / Applied Fix
1. **Declarative & Safe Systemd Service Unit**:
   Created `dotfiles/config/systemd/user/rclone-gdrive.service` with:
   - `ConditionPathExists=%h/.config/rclone/rclone.conf`: Prevents systemd from starting or failing the service on fresh machines prior to running `rclone config`.
   - `ExecStartPre=/usr/bin/mkdir -p %h/GoogleDrive %h/.cache/rclone`: Guarantees both the mountpoint and log/cache directories exist prior to invocation.
   - `Type=simple`: Avoids relying on Go systemd notification tags which are absent in standard Ubuntu packages (`go/tags: none`).
   - `ExecStop=/usr/bin/fusermount -u %h/GoogleDrive`: Ensures clean unmounting on service stop or shutdown.

2. **Dedicated Systemd Service Deployer in `03-dotfiles.sh`**:
   - Explicitly skipped `systemd` from the generic shallow directory symlinker in `deploy_xdg_configs`.
   - Added `deploy_systemd_user_services()` to symlink individual unit files (`*.service`) into `~/.config/systemd/user/` while preserving `~/.config/systemd/user/` as a native directory.
   - Automatically executes `systemctl --user daemon-reload` and `systemctl --user enable rclone-gdrive.service`.

3. **Cache Remediation**:
   - If an unclean shutdown leaves a large, rate-limited dirty cache, moving or clearing `~/.cache/rclone` restores instant mount performance.

4. **Remote Control (RC) Server for Telemetry & Diagnostics**:
   - Enabled `--rc --rc-addr=127.0.0.1:5572 --rc-no-auth` in the service definition.
   - Restricting to `127.0.0.1` prevents network exposure, while `--rc-no-auth` allows unauthenticated local querying of transfer speeds, remaining ETAs, and active uploads via `rclone rc core/stats`.

5. **Visual TUI Dashboard (`gdrive-stats`)**:
   - Replaced raw JSON dumps with a native `rich`-based terminal UI dashboard (`dotfiles/bin/gdrive-stats`, symlinked to `~/.local/bin/gdrive-stats`).
   - Visualizes live upload/download progress bars, transfer speeds, remaining ETAs, local VFS disk cache usage (vs 10G limit), Google Drive remote quota, and recent transfer history.
   - Built with adaptive terminal layout (auto-reflowing between 3-column and 2-column cards), non-blocking keyboard controls (`q` to quit, `r` to refresh, `f` to forget/drop VFS cache, `c` to reset counters), and non-interactive `--once` and `--json` modes.
   - Added `python3-rich` to `manifests/apt-packages.list` for declarative provisioning.

### 4. Replication Impact
- Added `rclone`, `kio-gdrive`, and `python3-rich` to `manifests/apt-packages.list`.
- Added `rclone.conf` to `.gitignore` to prevent credential leaks.
- Service and user binaries (`gdrive-stats`) are automatically provisioned and enabled during `./bootstrap.sh` (Stage 03).
- Added post-bootstrap guidance in `docs/replication-guide.md` to run `rclone config` for the `gdrive` remote and use `gdrive-stats` for monitoring.
