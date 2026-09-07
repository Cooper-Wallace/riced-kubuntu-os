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

# --- Starship Prompt ---
if command -v starship >/dev/null 2>&1; then
    eval "$(starship init bash)"
fi

