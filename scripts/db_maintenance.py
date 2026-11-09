"""Safe SQLite maintenance: online backup, offline restore, integrity verification."""
import argparse
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / 'data' / 'giveaways.sqlite3'


def integrity(db: Path):
    if not db.is_file():
        raise FileNotFoundError(f'Базу не знайдено: {db}')
    with sqlite3.connect(f'file:{db.resolve().as_posix()}?mode=ro', uri=True) as con:
        result = con.execute('PRAGMA integrity_check').fetchone()[0]
    if result != 'ok':
        raise RuntimeError(f'SQLite integrity_check: {result}')
    return result


def backup(db: Path, destination: Path):
    integrity(db)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError(f'Резервна копія вже існує: {destination}')
    tmp = destination.with_name(destination.name + '.incomplete')
    if tmp.exists():
        raise FileExistsError(f'Незавершена копія вже існує: {tmp}')
    try:
        with sqlite3.connect(f'file:{db.resolve().as_posix()}?mode=ro', uri=True) as src:
            with sqlite3.connect(tmp) as dst:
                src.backup(dst, pages=256, sleep=0.1)
        integrity(tmp)
        os.replace(tmp, destination)
    finally:
        tmp.unlink(missing_ok=True)
    return destination


def main():
    parser = argparse.ArgumentParser(description='Ayla SQLite backup / integrity / restore')
    parser.add_argument('command', choices=['backup', 'check', 'restore'])
    parser.add_argument('--db', type=Path, default=Path(os.getenv('GIVEAWAY_DB', DEFAULT_DB)))
    parser.add_argument('--file', type=Path, help='Backup destination or restore source')
    parser.add_argument('--yes-i-stopped-service', action='store_true', help='Required for restore')
    args = parser.parse_args()
    db = args.db.expanduser().resolve()
    if args.command == 'check':
        print(f'{db}: {integrity(db)}')
    elif args.command == 'backup':
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        target = args.file or (ROOT / 'backups' / f'giveaways_{stamp}.sqlite3')
        print(f'Backup created: {backup(db, target.resolve())}')
    else:
        if not args.file or not args.yes_i_stopped_service:
            parser.error('Restore requires --file and --yes-i-stopped-service')
        source = args.file.expanduser().resolve()
        integrity(source)
        if db.exists() or any(db.with_name(db.name + suffix).exists() for suffix in ('-wal', '-shm')):
            parser.error('Restore target exists. Stop the service and move current DB, -wal and -shm aside first.')
        db.parent.mkdir(parents=True, exist_ok=True)
        backup(source, db)
        print(f'Restored: {db}')


if __name__ == '__main__':
    try:
        main()
    except (OSError, sqlite3.Error, RuntimeError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        sys.exit(1)
