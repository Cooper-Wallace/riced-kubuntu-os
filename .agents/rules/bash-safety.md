# Bash Scripting Safety Standards

When authoring or modifying provisioning scripts in `scripts/`, `plasma/`, or the root `bootstrap.sh`:

1. **Strict Error Handling**:
   - Every script must begin with `set -euo pipefail` to ensure commands fail loudly and undefined variables are caught immediately.
   - Use standard traps for temporary file cleanup where applicable.

2. **Idempotency**:
   - Check if a package, repo, or config change has already been applied before applying it (e.g., `command -v foo >/dev/null || install_foo`).
   - For line additions (like shell aliases or environment variables), verify if the line or block already exists before appending.

3. **Portability & Permissions**:
   - Avoid running entire scripts under `sudo`. Scripts should be run by the regular user, invoking `sudo` only for specific system-level commands (e.g., `sudo apt update`).
   - Never assume hardcoded paths like `/home/cooper`. Always use `$HOME` or `"${XDG_CONFIG_HOME:-$HOME/.config}"`.

4. **Dry-Run Capability**:
   - Provide a `--dry-run` or `-n` flag in non-trivial setup scripts that echoes commands rather than executing system modifications.
