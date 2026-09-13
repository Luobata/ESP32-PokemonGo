#!/usr/bin/env bash
set -euo pipefail
server_host="${1:-devbox}"
server_bind="${2:-127.0.0.1}"
[[ "$server_bind" =~ ^[0-9.]+$ ]] || { echo "Bind must be an IPv4 address" >&2; exit 1; }
script_dir="$(cd "$(dirname "$0")" && pwd)"
ssh -o BatchMode=yes "$server_host" 'test -x /usr/bin/python3 && mkdir -p ~/.local/share/pokewalk-save-manager ~/.config/systemd/user'
tar -C "$script_dir" -czf - server.py web | ssh -o BatchMode=yes "$server_host" 'tar -xzf - -C ~/.local/share/pokewalk-save-manager'
ssh -o BatchMode=yes "$server_host" 'cat > ~/.config/systemd/user/pokewalk-save-manager.service' <<UNIT
[Unit]
Description=PokeWalk developer save manager (static UI only)
After=network.target
[Service]
ExecStart=/usr/bin/python3 %h/.local/share/pokewalk-save-manager/server.py --host $server_bind --port 8767
Restart=on-failure
RestartSec=3
NoNewPrivileges=true
[Install]
WantedBy=default.target
UNIT
ssh -o BatchMode=yes "$server_host" 'systemctl --user daemon-reload && systemctl --user enable pokewalk-save-manager.service && systemctl --user restart pokewalk-save-manager.service && systemctl --user is-active pokewalk-save-manager.service'
printf '通过 SSH 转发使用：ssh -N -L 8767:127.0.0.1:8767 %s\n网页：http://localhost:8767\n' "$server_host"
