# Package Management Hierarchy & Standards

When installing applications or updating manifests in `manifests/`:

1. **Hierarchy of Sources**:
   - **APT (Official Repositories)**: Preferred for core CLI tools, compilers, libraries, drivers, and system packages.
   - **Flatpak**: Preferred for desktop graphical applications where isolated sandboxing and up-to-date upstream packages are desirable (e.g., browsers, communication tools, media players).
   - **Snap**: Used when mandated by Ubuntu default distributions or canonical tools.
   - **Custom PPAs / Third-Party Repos**: Treat as last resort. Every PPA must be documented in `manifests/ppas.list` with its key and reason.

2. **Manifest Tracking**:
   - Do not capture auto-installed dependencies. Only capture manual packages (e.g., via `apt-mark showmanual`).
   - Whenever an agent runs an installation command on behalf of the user, prompt to add the package to the appropriate file in `manifests/`.
