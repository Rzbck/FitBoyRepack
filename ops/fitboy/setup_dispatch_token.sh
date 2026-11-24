#!/bin/bash
# Run interactively on the VPS, never with a token argument.
set -euo pipefail
set +x
[[ $EUID -eq 0 && -t 0 ]] || { echo "Run using sudo in an interactive SSH session."; exit 1; }
umask 077
read -r -s -p "Paste the dedicated GitHub fine-grained token (hidden): " token
printf '\n'
if [[ ! $token =~ ^github_pat_[A-Za-z0-9_]{20,}$ ]]; then
    unset token
    echo "Invalid token format; nothing changed."
    exit 1
fi
tmp=$(mktemp /etc/fitboy/.github-dispatch.XXXXXX)
trap 'rm -f "$tmp"; unset token' EXIT
printf '%s\n' "$token" > "$tmp"
unset token
chmod 0600 "$tmp"
chown root:root "$tmp"
mv -fT "$tmp" /etc/fitboy/github-dispatch.token
systemctl enable --now fitboy-dispatch.timer
systemctl start fitboy-dispatch.service
systemctl show fitboy-dispatch.service -p Result -p ActiveState
systemctl list-timers fitboy-dispatch.timer --no-pager
echo "Credential installed. Review the service journal for API status; never paste the token into chat."
