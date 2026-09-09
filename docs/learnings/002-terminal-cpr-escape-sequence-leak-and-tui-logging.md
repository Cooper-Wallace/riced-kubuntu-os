# 002 - Terminal CPR Escape Sequence Leak and Bootstrap TUI Overhaul

- **Date**: 2026-09-08
- **Target Component**: Bootstrap Orchestrator / TUI / Terminal Hygiene / Packaging
- **Environment**: Kubuntu 26.04 LTS (KDE Plasma 6, Konsole, Wayland)

---

### 1. Problem / Context
1. **Escape Sequence Dump**: Upon completing `./bootstrap.sh`, the interactive Konsole prompt was flooded with dozens of unrequested characters like `8;1R8;1R8;17R8;62R8;51R8;51R...`.
2. **Clunky Verbose Output**: Package installations (`apt-get`, `flatpak install`, repository updates) produced thousands of lines of noisy text directly on stdout, burying high-level status messages and making failures difficult to diagnose.

### 2. Root Cause Analysis
- **Cursor Position Report (CPR) Leaks**:
  - Interactive CLI utilities like `flatpak` and `apt` (with `DPkg::Progress-Fancy`) emit ANSI CPR queries (`\033[6n`) to determine the cursor row/column when drawing dynamic download progress animations.
  - The terminal responds to these queries by sending `\033[<row>;<col>R` back to the terminal's stdin buffer (in this case, row 8: `8;1R`, `8;68R`).
  - In `scripts/02-snaps-flatpaks.sh`, `flatpak install` was executed inside a `while read ... done < "${FLATPAK_LIST}"` loop. Because stdin was redirected from the manifest file, `flatpak` did not consume the terminal's CPR response from the tty.
  - Consequently, dozens of `8;XXR` responses queued in the kernel tty input buffer and were read by Bash's readline immediately after the script exited.
- **Unbuffered Verbose Stdout**:
  - Running package managers directly in the foreground without log redirection caused massive terminal spam.

### 3. Solution / Applied Fix
1. **Centralized Log Redirection & Spinner Animation** (`scripts/lib/common.sh`):
   - Implemented `spin_task()`: when running in an interactive terminal, it displays a clean, animated spinner (`⠋ ⠙ ⠹...`) while redirecting all stdout and stderr to `logs/bootstrap-YYYYMMDD-HHMMSS.log` (symlinked as `logs/latest.log`).
   - If a task fails, `spin_task` prints `✖ <task>` and automatically displays the last 20 lines of the log for instant diagnosis.
2. **Eliminated CPR Leaks**:
   - Switched loop processing to array parsing (`mapfile -t FLATPAKS`) rather than redirecting stdin on the loop.
   - Added `--non-interactive` and `< /dev/null` to `flatpak install`.
   - Disabled APT fancy progress (`-o DPkg::Progress-Fancy="0"`) and set `DEBIAN_FRONTEND=noninteractive`.
3. **Pre-flight Sudo & Terminal Hygiene** (`bootstrap.sh`):
   - Added upfront `sudo -v` validation and background keepalive so password prompts do not hang behind redirected logs.
   - Added a cleanup trap on EXIT/INT/TERM to restore cursor visibility (`\033[?25h\033[0m`), reset terminal modes (`stty echo`), and drain any remaining input buffer bytes (`while read -r -t 0.05 -n 10000 _discard; do :; done`).

### 4. Replication Impact
- Future bootstrap executions on fresh Kubuntu machines produce clean, distraction-free TUI progress with zero terminal corruption or prompt leakage.
