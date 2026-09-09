# Dotfiles Management

Dotfiles in this folder are organized in a format compatible with [GNU Stow](https://www.gnu.org/software/stow/) and the custom symlink orchestrator in `scripts/03-dotfiles.sh`.

## Structure
Each top-level directory mirrors the target structure relative to `$HOME`:
- `bash/`: Contains files targeted for `~/` (e.g. `.bash_aliases`)
- `readline/`: Contains `.inputrc` targeted for `~/` (case-insensitive tab completion & prefix search)
- `tmux/`: Contains `.tmux.conf` targeted for `~/` (modern Ctrl-a multiplexer with Catppuccin Mocha)
- `config/`: Applications and configurations meant for `~/.config/` (`fastfetch/`, `fontconfig/`, `gtk-3.0/`, `gtk-4.0/`, `starship.toml`, `dolphinrc`, `krunnerrc`, `systemd/user/rclone-gdrive.service`)
- `konsole/`: Custom KDE Konsole profiles (`RKO.profile`) and color schemes (`CatppuccinMocha.colorscheme`) deployed to `~/.local/share/konsole/`


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
