# Dotfiles Management

Dotfiles in this folder are organized in a format compatible with [GNU Stow](https://www.gnu.org/software/stow/) and the custom symlink orchestrator in `scripts/03-dotfiles.sh`.

## Structure
Each top-level directory mirrors the target structure relative to `$HOME`:
- `bash/`: Contains files targeted for `~/` (e.g. `.bash_aliases`, `.bashrc.custom`)
- `config/`: Contains applications meant for `~/.config/` (e.g. `kitty/`, `fastfetch/`, `nvim/`)

## Applying Dotfiles Manually
Using GNU Stow:
```bash
# Stow bash configs into $HOME
stow -d dotfiles -t ~ bash

# Stow .config items into ~/.config
stow -d dotfiles/config -t ~/.config .
```
Or use the automated script:
```bash
./scripts/03-dotfiles.sh
```
