#!/usr/bin/env python3
"""Create and validate a private, rotating SQLite backup for the Dishly VM."""

import os
import sqlite3
import time
from datetime import datetime
from pathlib import Path

DATABASE = Path("/home/keka/D1shlyBot/dishly.sqlite3")
BACKUP_DIR = Path("/home/keka/backups/dishly")


def main():
    if not DATABASE.is_file():
        raise SystemExit(f"Database not found: {DATABASE}")

    os.umask(0o077)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(BACKUP_DIR, 0o700)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = BACKUP_DIR / f"dishly-{stamp}.sqlite3"
    temporary = BACKUP_DIR / f".dishly-{stamp}.tmp"

    source = sqlite3.connect(f"file:{DATABASE}?mode=ro", uri=True, timeout=30)
    target = None
    try:
        target = sqlite3.connect(temporary)
        source.backup(target)
        result = target.execute("PRAGMA integrity_check").fetchone()[0]
        if result != "ok":
            raise RuntimeError(f"Backup integrity check failed: {result}")
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    finally:
        source.close()
        if target is not None:
            target.close()

    os.replace(temporary, backup)
    os.chmod(backup, 0o600)

    cutoff = time.time() - 14 * 24 * 60 * 60
    for old_backup in BACKUP_DIR.glob("dishly-*.sqlite3"):
        if old_backup != backup and old_backup.stat().st_mtime < cutoff:
            old_backup.unlink()

    print(f"Backup created: {backup} ({backup.stat().st_size} bytes); integrity: ok")


if __name__ == "__main__":
    main()
