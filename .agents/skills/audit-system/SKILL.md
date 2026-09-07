---
name: audit-system
description: Use this skill when auditing the current machine state against the repository manifests (APT, Flatpak, Snap, PPAs) to detect uncommitted packages or configuration drift.
---

# Audit System Against Manifests

This skill provides the verification sequence to check if the current machine has packages or configurations that have not yet been recorded in `manifests/`.

## Procedure

1. **Audit APT Manual Packages**:
   Compare manually installed packages with `manifests/apt-packages.list`:
   ```bash
   comm -13 <(sort -u manifests/apt-packages.list) <(apt-mark showmanual | sort -u)
   ```
   Filter out standard Ubuntu desktop base metapackages and ask the user if any newly installed tools should be committed.

2. **Audit Flatpaks & Snaps**:
   - For Flatpaks: `flatpak list --app --columns=application` vs `manifests/flatpaks.list`
   - For Snaps: `snap list` vs `manifests/snaps.list`

3. **Audit PPAs & Software Sources**:
   Inspect `/etc/apt/sources.list.d/` and verify that any external repositories or keys are documented in `manifests/ppas.list`.

4. **Summarize Drift**:
   Present any untracked packages or drift in a concise table and offer to update the manifests.
