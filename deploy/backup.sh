#!/bin/sh
# Nightly encrypted backups: Postgres dump + knowledge uploads + encrypted WhatsApp session.
# Files are AES-256 encrypted with BACKUP_KEY (keep a copy of that key OFF the server, e.g. your password manager).
# Restore: openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -pass env:BACKUP_KEY -in X.enc | ...
set -eu
apk add --no-cache openssl >/dev/null 2>&1 || true
enc() { openssl enc -aes-256-cbc -pbkdf2 -iter 200000 -salt -pass env:BACKUP_KEY -out "$1"; }
while true; do
  ts=$(date -u +%Y%m%d-%H%M)
  pg_dump --format=custom | enc "/backups/db-$ts.dump.enc"
  tar -C /src -cz storage/uploads session 2>/dev/null | enc "/backups/files-$ts.tgz.enc" || true
  find /backups -name '*.enc' -mtime +"$KEEP_DAYS" -delete
  echo "backup $ts ok"
  sleep 86400
done
