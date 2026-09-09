# --- RKO Custom Aliases ---
if command -v eza >/dev/null 2>&1; then
    alias ls='eza --icons=auto'
    alias ll='eza -lh --icons=auto --git'
    alias la='eza -a --icons=auto'
    alias lt='eza --tree --level=2 --icons=auto'
else
    alias ll='ls -alF'
    alias la='ls -A'
    alias l='ls -CF'
fi

# Modern cat / syntax highlighter
if command -v batcat >/dev/null 2>&1; then
    alias cat='batcat --paging=never'
    alias bat='batcat'
elif command -v bat >/dev/null 2>&1; then
    alias cat='bat --paging=never'
fi

# Resource monitor
if command -v btop >/dev/null 2>&1; then
    alias top='btop'
fi

# Git shortcuts
alias gs='git status'
alias gp='git pull'
alias gd='git diff'

# System convenience
alias update-all='sudo apt update && sudo apt upgrade -y'

# --- Smart Navigation & Fuzzy Finding ---
if command -v zoxide >/dev/null 2>&1; then
    eval "$(zoxide init bash)"
fi

if command -v fzf >/dev/null 2>&1; then
    eval "$(fzf --bash 2>/dev/null || fzf --key-bindings 2>/dev/null || true)"
fi

# --- Readline Custom Configuration ---
if [[ -f "${HOME}/.inputrc" ]]; then
    export INPUTRC="${HOME}/.inputrc"
fi

# --- Starship Prompt ---
if command -v starship >/dev/null 2>&1; then
    eval "$(starship init bash)"
fi

# --- Interactive Fuzzy Workflows (ripgrep + fzf + bat) ---
# Find in files with syntax-highlighted live preview
fif() {
    if ! command -v rg >/dev/null 2>&1 || ! command -v fzf >/dev/null 2>&1; then
        echo "Error: ripgrep and fzf are required for fif."
        return 1
    fi
    local query="${1:-}"
    local bat_cmd="bat --color=always --style=numbers --line-range=:500 {}"
    command -v batcat >/dev/null 2>&1 && bat_cmd="batcat --color=always --style=numbers --line-range=:500 {}"

    rg --color=always --line-number --no-heading --smart-case "${query}" | \
        fzf --ansi \
            --color "hl:-1:underline,hl+:-1:underline:reverse" \
            --delimiter : \
            --preview "${bat_cmd}" \
            --preview-window 'up,60%,border-bottom,+{2}+3/3,~3'
}

# --- Google Drive & Storage Diagnostics ---
alias gdrive-status='systemctl --user status rclone-gdrive.service'
alias gdrive-stats='gdrive-stats'
alias gdrive-stats-raw='rclone rc core/stats'
alias gdrive-import='gdrive-import'
alias gdrive-log='journalctl --user -u rclone-gdrive.service -f'
