# Server deployment files

These files capture the current Cloud.ru VM setup for the `keka` account and project path `/home/keka/D1shlyBot`.

- `systemd/mihomo.service` starts Mihomo and pulls in Dishly when the proxy starts.
- `systemd/dishly.service` runs the Telegram bot after Mihomo.
- `backup/dishly-backup-db.py` creates a validated SQLite copy outside the repository and keeps 14 days.
- `systemd/dishly-backup.service` and `systemd/dishly-backup.timer` run that backup daily around 03:00.

Never commit `.env`, `nevpn.yaml`, subscription URLs, credentials, or generated Mihomo rule files. The project contains only service definitions and the backup utility.

To install updated unit definitions from the project root, first back up the active unit files, then run:

```bash
sudo cp /etc/systemd/system/mihomo.service /etc/systemd/system/mihomo.service.bak
sudo cp /etc/systemd/system/dishly.service /etc/systemd/system/dishly.service.bak
sudo install -m 0644 deploy/systemd/mihomo.service /etc/systemd/system/mihomo.service
sudo install -m 0644 deploy/systemd/dishly.service /etc/systemd/system/dishly.service
sudo install -m 0644 deploy/systemd/dishly-backup.service /etc/systemd/system/dishly-backup.service
sudo install -m 0644 deploy/systemd/dishly-backup.timer /etc/systemd/system/dishly-backup.timer
sudo install -m 0755 deploy/backup/dishly-backup-db.py /usr/local/bin/dishly-backup-db.py
sudo systemctl daemon-reload
sudo systemctl enable mihomo.service dishly.service dishly-backup.timer
```

Then restart the services whose unit files changed and verify them with `systemctl status`. Updating the backup script does not require restarting Dishly.
