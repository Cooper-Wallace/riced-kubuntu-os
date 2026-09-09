# Privacy Policy for Riced-Kubuntu-OS (RKO)

**Last updated:** September 9, 2026

This Privacy Policy describes how the **Riced-Kubuntu-OS** project ("we", "us", or "our") handles your personal data, credentials, and files when you interact with Google Drive via our custom automation tools, system services, and local scripts (including `rclone-gdrive.service`, `gdrive-stats`, and `gdrive-import`).

---

## 1. Overview & Architecture

**Riced-Kubuntu-OS** is an open-source, personal Linux operating system configuration and dotfiles framework. All components operate strictly client-side on your local machine.

- **No Remote Servers**: We do not operate intermediate proxy servers, telemetry endpoints, or cloud backends.
- **Direct Communication**: All network communications occur directly and encrypted (HTTPS/TLS) between your local machine and official Google APIs (`www.googleapis.com`).
- **Self-Hosted Credentials**: Your OAuth tokens, client credentials, and configuration files reside exclusively on your local filesystem under your user account.

---

## 2. Information We Access and Process

When you authorize the Riced-Kubuntu-OS application with your Google Account, the application accesses only the scopes necessary to perform the requested filesystem and backup operations:

1. **Google Drive Files and Metadata (`https://www.googleapis.com/auth/drive` or `https://www.googleapis.com/auth/drive.file`)**:
   - Access is used exclusively to list, read, upload, download, and check integrity hashes (MD5) of files you select for synchronization or offloading (such as camera SD card media).
2. **Account Identifier & Email**:
   - Used solely to display authentication status and available cloud storage quota in the local terminal UI (`gdrive-stats`).

---

## 3. How Information is Used

Information accessed via Google APIs is used strictly to:
- Present a persistent, local FUSE filesystem mount point (`~/GoogleDrive`) on your workstation.
- Stream media and documents directly between local storage (e.g. camera SD cards) and your Google Drive storage.
- Calculate storage quotas, upload throughput, and transfer progress inside the local `gdrive-stats` monitoring dashboard.
- Perform cryptographic checksum verification (MD5) to prevent accidental data overwrites and avoid redundant re-uploads.

---

## 4. Data Storage and Security

- **Local Storage of Credentials**: OAuth access and refresh tokens are stored locally on your machine at `~/.config/rclone/rclone.conf`. This file is created with restricted user-only permissions (`0600`).
- **No Third-Party Transmission**: We do not sell, rent, monetize, or transmit your credentials, personal data, or Google Drive files to any third party.
- **Git Safety**: The `riced-kubuntu-os` repository explicitly ignores `rclone.conf` and all private token files in its `.gitignore` to prevent inadvertent disclosure.

---

## 5. Google API Services User Data Policy (Limited Use Disclosure)

Riced-Kubuntu-OS's use and transfer to any other app of information received from Google APIs will adhere to the [Google API Services User Data Policy](https://developers.google.com/terms/api-services-user-data-policy), including the **Limited Use** requirements.

We do not use Google user data to train generalized artificial intelligence or machine learning models.

---

## 6. User Control & Revoking Access

You maintain complete control over your data and access permissions:
- **Local Removal**: You can remove local credentials at any time by deleting `~/.config/rclone/rclone.conf` or executing `rclone config disconnect gdrive:`.
- **Google Account Revocation**: You can revoke access granted to this application at any time by visiting your [Google Account Third-party apps & services settings](https://myaccount.google.com/connections).

---

## 7. Open Source Source Code

The complete source code of all tools, scripts, and service definitions that interact with Google Drive is transparently audited and available in the public repository:
- **Repository**: [https://github.com/Cooper-Wallace/riced-kubuntu-os](https://github.com/Cooper-Wallace/riced-kubuntu-os)

---

## 8. Contact & Inquiries

For questions or inquiries regarding this Privacy Policy or the security practices of this project, please open an issue on the repository:
- **Issues**: [https://github.com/Cooper-Wallace/riced-kubuntu-os/issues](https://github.com/Cooper-Wallace/riced-kubuntu-os/issues)
- **Maintainer**: Cooper Wallace
