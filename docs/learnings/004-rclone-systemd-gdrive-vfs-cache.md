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
   - Visualizes live upload/download progress bars, transfer speeds, remaining ETAs, local VFS disk cache usage (vs 15G limit), Google Drive remote quota, and recent transfer history.
   - Built with adaptive terminal layout (auto-reflowing between 3-column and 2-column cards), non-blocking keyboard controls (`q` to quit, `r` to refresh, `f` to forget/drop VFS cache, `c` to reset counters), and non-interactive `--once` and `--json` modes.
   - Proactive 403 Rate Limit Badge: Automatically detects when Google Drive API rate limits are exceeded, displaying a warning badge and guidance in the header and diagnostics panel.
   - Added `python3-rich` to `manifests/apt-packages.list` for declarative provisioning.

6. **Root Cause & Resolution for Bulk Camera Media Upload Performance**:
   - **Shared Client ID Rate Limiting (`403 RATE_LIMIT_EXCEEDED`)**:
     - When queuing 842 files (6.81 GB) of camera photos/RAW files, uploads repeatedly froze for 10-45 minutes.
     - Logs confirmed Google API rate-limiting against `project_number:202264815644` (the default shared rclone client ID). When thousands of users share this global project quota, Google imposes exponential backoff delays on file finalization calls.
   - **Chunk Size Fragmentation**:
     - Default `--drive-chunk-size 8Mi` and `--drive-upload-cutoff 8Mi` forced every single 8.5MB–25MB camera photo into multiple chunked resumable upload requests, multiplying API transactions by 5x-10x.
   - **Live In-Flight Mitigation**:
     - Applied runtime pacing via `rclone rc options/set` (`TPSLimit: 10`, `TPSLimitBurst: 2`, `Transfers: 2`, `LowLevelRetries: 5`) without unmounting the live drive.
   - **Mount Service Optimization**:
     - Updated `dotfiles/config/systemd/user/rclone-gdrive.service` with `--drive-chunk-size 64M`, `--drive-upload-cutoff 64M`, `--tpslimit 10`, `--vfs-write-back 15s`, `--transfers 3`, and `--fast-list`.
   - **Dedicated Camera Media Offloader (`gdrive-import`)**:
     - Created `dotfiles/bin/gdrive-import` (symlinked to `~/.local/bin/gdrive-import`).
     - Auto-detects mounted camera SD card root volumes (`/run/media/$USER/<LABEL>` or `/media/$USER/<LABEL>`).
     - Target Google Drive Root: `Media/Raw Camera Files` (cleanly distinguishing unedited camera media from future edits).
     - **Two-Stage Modular Pipeline**:
       - **Stage 1 (Photos)**: Scans `DCIM/` for camera photos (`.JPG`, `.ARW`, `.CR2`, `.NEF`, `.DNG`, etc.), parses capture date via EXIF `DateTimeOriginal` / `DateTimeDigitized`, and uploads directly to `Media/Raw Camera Files/YYYY/MM/<photo_file>`.
       - **Stage 2 (Videos & Sidecars)**: Scans video folders (`PRIVATE/M4ROOT/CLIP`, etc.) for video clips (`.MP4`, `.MOV`) and pairs them with their shooting sidecars (`.XML`), uploading to `Media/Raw Camera Files/YYYY/MM/videos/<video_file>`.
     - **Hardware Folder Flattening**: Automatically strips camera hardware containers (`100MSDCF`, `DCIM`, `PRIVATE`, `CLIP`) while safely bypassing camera database folders (`AVF_INFO/`, `BDMV/`, `THMBNL/`).
     - **Selective Execution Flags**: Supports `--photos-only` (offload only photos) and `--videos-only` (offload only video clips and paired sidecars).
     - **Built-in Deduplication**: Runs with `--checksum` comparing MD5 hashes against Google Drive's native file hashes (skips identical media without re-uploading bytes).
     - Supports `--ignore-existing`, `--delete-source` (safely frees SD card space only after verified cloud transfer), and `--verify`.

### 4. Replication Impact
- Added `rclone`, `kio-gdrive`, and `python3-rich` to `manifests/apt-packages.list`.
- Added `rclone.conf` to `.gitignore` to prevent credential leaks.
- Service and user binaries (`gdrive-stats`, `gdrive-import`) are automatically provisioned and enabled during `./bootstrap.sh` (Stage 03).
- Added post-bootstrap guidance in `docs/replication-guide.md` for configuring a personal Google Cloud OAuth Client ID to completely bypass public rate limits.
