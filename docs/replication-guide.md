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
3. Configure Google Drive Mount (Rclone):
   - Run `rclone config` to create a new remote named `gdrive` targeting Google Drive.
   - The user service `rclone-gdrive.service` is deployed and enabled by Stage 03, and will automatically mount to `~/GoogleDrive` once `~/.config/rclone/rclone.conf` exists.
