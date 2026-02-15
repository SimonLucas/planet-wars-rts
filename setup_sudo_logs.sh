#!/usr/bin/env bash
# Configure passwordless sudo for log cleanup operations used by the league

cat <<'EOF' | sudo tee /etc/sudoers.d/planet-wars-logs
# Allow passwordless sudo for log cleanup commands used by planet-wars league
simonlucas ALL=(ALL) NOPASSWD: /usr/bin/truncate -s 0 /var/log/syslog
simonlucas ALL=(ALL) NOPASSWD: /usr/bin/truncate -s 0 /var/log/syslog.1
simonlucas ALL=(ALL) NOPASSWD: /usr/bin/journalctl --rotate
simonlucas ALL=(ALL) NOPASSWD: /usr/bin/journalctl --vacuum-size=*
EOF

sudo chmod 440 /etc/sudoers.d/planet-wars-logs
sudo visudo -c

echo ""
echo "✅ Passwordless sudo configured for log cleanup commands"
echo "You can now run ./start_league.sh without password prompts"
