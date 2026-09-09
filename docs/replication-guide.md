# Machine Replication Guide

Follow this guide when bootstrapping a fresh Kubuntu machine to match this development environment.

## Phase 1: Clean OS Installation
1. Install **Kubuntu 26.04 LTS**.
2. Select standard installation with third-party graphics/Wi-Fi drivers if prompted.
3. During user creation, note the primary username.

## Phase 2: Post-Install Baseline & Git Access
1. Open a terminal and update package lists:
   ```bash
   sudo apt update && sudo apt upgrade -y
   sudo apt install -y git curl ca-certificates
   ```
2. Clone this repository into `~/Projects/riced-kubuntu-os`:
   ```bash
   mkdir -p ~/Projects
   git clone https://github.com/Cooper-Wallace/riced-kubuntu-os.git ~/Projects/riced-kubuntu-os
   cd ~/Projects/riced-kubuntu-os
   ```

## Phase 3: Automated Provisioning
1. Review pending actions with a dry-run:
   ```bash
   ./bootstrap.sh --dry-run
   ```
2. Run the complete bootstrap:
   ```bash
   ./bootstrap.sh
   ```

## Phase 4: Verification & KDE Plasma Reload
1. Log out and log back into the Wayland session to ensure all Plasma theme engines, shortcuts, and environment variables take effect.
2. Run system audit to check for drift:
   - Consult `.agents/skills/audit-system/SKILL.md`.
3. Configure Google Drive Mount & Camera Offload (Rclone):
   - Run `rclone config` to create a new remote named `gdrive` targeting Google Drive.
   - **Recommended (High Performance & No 403 Rate Limits)**:
     - Set up your own free Google Cloud Client ID & Client Secret instead of leaving them blank:
       1. Visit [Google Cloud Console](https://console.cloud.google.com/) and create a project (e.g. `RKO-Storage`).
       2. Enable the **Google Drive API** in APIs & Services.
       3. Under **OAuth consent screen**, select *External*, set User Support Email, and add your Google account to *Test users*.
       4. Under **Credentials**, create **OAuth client ID** (Application type: *Desktop app*).
       5. Provide your `client_id` and `client_secret` during `rclone config` (or edit `~/.config/rclone/rclone.conf`).
   - The user service `rclone-gdrive.service` is deployed and enabled by Stage 03, and will automatically mount to `~/GoogleDrive` once `~/.config/rclone/rclone.conf` exists.
   - **Monitor Mount Status**: Use `gdrive-stats` (interactive TUI dashboard), `gdrive-stats-raw` (raw JSON), `gdrive-status` (systemd status), or `gdrive-log` (systemd journal).
   - **High-Throughput Camera Offloading**:
     - When transferring bulk photos/videos from an SD card, run `gdrive-import` (or `gdrive-import /path/to/DCIM`).
     - Supports direct cloud streaming with 128MB chunks, `--delete-source` to safely free SD card storage after verified upload, and `--verify` for MD5 hash integrity verification.
